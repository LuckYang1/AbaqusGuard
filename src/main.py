"""
Abaqus 作业监控主程序
监控 Abaqus 计算作业，通过飞书推送通知
"""
import sys
import time
from datetime import datetime
from typing import Dict

from src.config.settings import get_settings
from src.core.job_detector import JobDetector
from src.feishu.webhook_client import get_webhook_client
from src.models.job import JobInfo


class AbaqusMonitor:
    """Abaqus 作业监控器"""

    def __init__(self):
        """初始化监控器"""
        self.settings = get_settings()
        self.detector = JobDetector()
        self.webhook = get_webhook_client()

        # 跟踪已处理的作业
        self.tracked_jobs: Dict[str, JobInfo] = {}
        # 上次进度通知时间
        self.last_progress_notify: Dict[str, datetime] = {}

    def run(self):
        """运行监控循环"""
        self._log("=== Abaqus 作业监控启动 ===")
        self._log(f"监控目录: {self.settings.WATCH_DIRS}")
        self._log(f"轮询间隔: {self.settings.POLL_INTERVAL} 秒")
        self._log(f"进度推送间隔: {self.settings.PROGRESS_NOTIFY_INTERVAL} 秒")

        try:
            while True:
                self._scan_once()
                time.sleep(self.settings.POLL_INTERVAL)

        except KeyboardInterrupt:
            self._log("=== 监控已停止 ===")

    def _scan_once(self):
        """执行一次扫描"""
        try:
            # 扫描所有目录
            all_jobs = self.detector.scan_directories()

            # 处理新作业
            for job in all_jobs:
                job_key = self._get_job_key(job)

                if job_key not in self.tracked_jobs:
                    # 新作业
                    self._on_job_start(job)
                    self.tracked_jobs[job_key] = job
                else:
                    # 已跟踪的作业，更新状态
                    tracked_job = self.tracked_jobs[job_key]
                    self._update_tracked_job(tracked_job, job)

                    # 检查是否完成
                    if job.is_completed:
                        self._on_job_complete(job)
                        # 从跟踪列表移除
                        self.tracked_jobs.pop(job_key, None)
                        self.last_progress_notify.pop(job_key, None)
                    else:
                        # 检查是否需要发送进度通知
                        self._check_progress_notify(job)

        except Exception as e:
            self._log(f"扫描异常: {e}")

    def _on_job_start(self, job: JobInfo):
        """处理作业开始事件"""
        self._log(f"作业开始: {job.name} @ {job.work_dir}")

        # 发送 Webhook 通知
        if self.settings.FEISHU_WEBHOOK_URL:
            self.webhook.send_job_start(job)

    def _on_job_complete(self, job: JobInfo):
        """处理作业完成事件"""
        self._log(f"作业完成: {job.name} - {job.status.value}")

        # 孤立作业已在 detector 中发送警告通知，跳过
        if job.is_orphan:
            return

        # 发送 Webhook 通知
        if self.settings.FEISHU_WEBHOOK_URL:
            self.webhook.send_job_complete(job)

    def _update_tracked_job(self, tracked: JobInfo, current: JobInfo):
        """更新已跟踪作业的状态"""
        tracked.step = current.step
        tracked.increment = current.increment
        tracked.total_time = current.total_time
        tracked.step_time = current.step_time
        tracked.inc_time = current.inc_time
        tracked.status = current.status

    def _check_progress_notify(self, job: JobInfo):
        """检查是否需要发送进度通知"""
        if self.settings.PROGRESS_NOTIFY_INTERVAL <= 0:
            return

        job_key = self._get_job_key(job)
        last_notify = self.last_progress_notify.get(job_key)
        now = datetime.now()

        if not last_notify:
            # 第一次运行，立即发送初始进度通知
            self.last_progress_notify[job_key] = now
            self._log(f"进度更新: {job.name} - Step:{job.step} Inc:{job.increment}")

            if self.settings.FEISHU_WEBHOOK_URL:
                self.webhook.send_job_progress(job)
            return

        elapsed = (now - last_notify).total_seconds()

        if elapsed >= self.settings.PROGRESS_NOTIFY_INTERVAL:
            self._log(f"进度更新: {job.name} - Step:{job.step} Inc:{job.increment}")

            if self.settings.FEISHU_WEBHOOK_URL:
                self.webhook.send_job_progress(job)

            self.last_progress_notify[job_key] = now

    def _get_job_key(self, job: JobInfo) -> str:
        """获取作业唯一标识"""
        return f"{job.name}@{job.work_dir}"

    def _log(self, message: str):
        """输出日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")


def main():
    """主函数"""
    settings = get_settings()

    # 检查配置
    if not settings.WATCH_DIRS:
        print("错误: 未配置监控目录 (WATCH_DIRS)")
        sys.exit(1)

    # 启动监控
    monitor = AbaqusMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
