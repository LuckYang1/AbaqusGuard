"""
作业检测器
通过监控 .lck 文件检测 Abaqus 作业的开始和结束
"""
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from src.config.settings import get_settings
from src.core.progress_parser import StaParser, get_job_info
from src.core.process_detector import get_process_detector
from src.feishu.webhook_client import get_webhook_client
from src.models.job import JobInfo, JobStatus


class JobDetector:
    """Abaqus 作业检测器"""

    def __init__(self):
        """初始化检测器"""
        self.settings = get_settings()
        self.process_detector = get_process_detector()
        self.webhook = get_webhook_client()
        self.running_jobs: Dict[str, JobInfo] = {}  # 正在运行的作业
        self.completed_jobs: List[JobInfo] = []      # 已完成的作业
        self.warned_orphan_lck: Set[str] = set()     # 已警告的孤立 .lck 文件

    def scan_directories(self) -> List[JobInfo]:
        """
        扫描所有监控目录，检测作业状态

        Returns:
            所有检测到的作业列表（包括运行中和已完成）
        """
        all_jobs = []

        for watch_dir in self.settings.WATCH_DIRS:
            jobs = self._scan_directory(Path(watch_dir))
            all_jobs.extend(jobs)

        return all_jobs

    def _scan_directory(self, directory: Path) -> List[JobInfo]:
        """扫描单个目录"""
        jobs = []

        if not directory.exists():
            if self.settings.VERBOSE:
                print(f"目录不存在: {directory}")
            return jobs

        # 查找所有 .lck 文件
        lck_files = list(directory.glob("*.lck"))
        current_lck = {f.stem for f in lck_files}  # 当前存在的 .lck 文件集合

        for lck_file in lck_files:
            # .lck 文件名格式为 {job_name}.lck
            job_name = lck_file.stem
            sta_file = directory / f"{job_name}.sta"

            # 检查是否是新作业或已跟踪的作业
            job_key = f"{job_name}@{directory}"

            if job_key in self.running_jobs:
                # 已跟踪的作业,更新状态
                job = self.running_jobs[job_key]
                self._update_job_progress(job, sta_file)

                # 检查作业是否变成孤立（进程停止但 .lck 未删除）
                if self.settings.ENABLE_PROCESS_DETECTION:
                    abaqus_running = self.process_detector.is_abaqus_running()
                    if not abaqus_running:
                        lck_age = self._get_lck_age(directory, job_name)
                        if lck_age >= self.settings.LCK_GRACE_PERIOD:
                            # 超过宽限期且无进程，判定为孤立
                            self._handle_orphan_job(job, sta_file)
                            # 添加到孤立列表，避免重复处理
                            self.warned_orphan_lck.add(job_key)
                            self.running_jobs.pop(job_key, None)
                            continue

                # 检查是否已完成
                if not lck_file.exists():
                    # .lck 文件被删除，作业可能完成
                    self._finalize_job(job, sta_file)
                # 无论是否完成，都添加到返回列表，以便 main.py 处理
                jobs.append(job)
            else:
                # 新作业 - 检查是否在孤立列表中
                if job_key in self.warned_orphan_lck:
                    # 之前是孤立文件，检查 .lck 是否被清理
                    if not lck_file.exists():
                        # .lck 已被清理，从孤立列表移除
                        self.warned_orphan_lck.discard(job_key)
                    continue

                # 检查是否应该作为新作业处理
                should_handle = self._check_new_job(directory, job_name, lck_file)
                if should_handle:
                    job = self._create_new_job(job_name, directory, sta_file, lck_file)
                    if job:
                        self.running_jobs[job_key] = job
                        jobs.append(job)

        # 检查之前运行的作业是否已完成
        self._check_completed_jobs(directory)

        return jobs

    def _check_new_job(self, directory: Path, job_name: str, lck_file: Path) -> bool:
        """
        检查新 .lck 文件是否应该作为新作业处理

        Args:
            directory: 目录路径
            job_name: 作业名称
            lck_file: .lck 文件路径

        Returns:
            是否应该作为新作业处理
        """
        if not self.settings.ENABLE_PROCESS_DETECTION:
            return True

        # 对于新发现的 .lck 文件，先作为新作业处理
        # 孤立文件检测在后续轮询中进行
        abaqus_running = self.process_detector.is_abaqus_running()

        if abaqus_running:
            # 进程在运行，作为新作业处理
            return True
        else:
            # 进程未运行，检查 .lck 文件年龄
            lck_age = self._get_lck_age(directory, job_name)
            if lck_age < self.settings.LCK_GRACE_PERIOD:
                # 在宽限期内，假设是新作业（进程可能还在启动）
                if self.settings.VERBOSE:
                    print(f"新 .lck 文件 ({int(lck_age)}秒)，等待进程启动: {job_name}")
                return True
            else:
                # 超过宽限期但进程未运行，可能是孤立文件
                # 但仍然先作为新作业处理，在下次轮询时再检查是否变成孤立
                if self.settings.VERBOSE:
                    print(f".lck 文件已存在 {int(lck_age)} 秒，进程未运行: {job_name}")
                    print(f"   先作为新作业处理，后续轮询再检查状态")
                return True

    def _get_lck_age(self, directory: Path, job_name: str) -> float:
        """
        获取 .lck 文件的年龄（自创建以来的秒数）

        Args:
            directory: 目录路径
            job_name: 作业名称

        Returns:
            .lck 文件存在的秒数，如果文件不存在则返回 0
        """
        lck_path = directory / f"{job_name}.lck"
        if lck_path.exists():
            create_time = lck_path.stat().st_ctime
            return time.time() - create_time
        return 0

    def _create_new_job(self, job_name: str, work_dir: Path, sta_file: Path, lck_file: Path) -> Optional[JobInfo]:
        """创建新作业信息"""
        try:
            # 使用 .lck 文件的创建时间作为作业开始时间
            start_time = datetime.fromtimestamp(lck_file.stat().st_ctime)

            job = JobInfo(
                name=job_name,
                work_dir=str(work_dir),
                computer=socket.gethostname(),
                start_time=start_time,
                status=JobStatus.RUNNING,
            )

            # 解析初始进度
            self._update_job_progress(job, sta_file)

            if self.settings.VERBOSE:
                print(f"检测到新作业: {job_name} @ {work_dir}")

            return job

        except Exception as e:
            print(f"创建新作业失败 {job_name}: {e}")
            return None

    def _update_job_progress(self, job: JobInfo, sta_file: Path):
        """更新作业进度"""
        try:
            result = StaParser(sta_file).parse()
            job.step = result.get("step", 0)
            job.increment = result.get("increment", 0)
            job.total_time = result.get("total_time", 0.0)
            job.step_time = result.get("step_time", 0.0)
            job.inc_time = result.get("inc_time", 0.0)

        except Exception as e:
            if self.settings.VERBOSE:
                print(f"更新作业进度失败 {job.name}: {e}")

    def _finalize_job(self, job: JobInfo, sta_file: Path):
        """完成作业，确定最终状态"""
        try:
            status_str = StaParser.get_status_from_file(sta_file)

            if status_str == "success":
                job.mark_completed(JobStatus.SUCCESS, "计算成功完成 - 收敛正常，结果可用")
            elif status_str == "failed":
                job.mark_completed(JobStatus.FAILED, "计算失败 - 分析未完成")
            else:
                # .lck 文件被删除但状态不明确
                job.mark_completed(JobStatus.ABORTED, "作业异常终止 - 状态未知")

            # 计算耗时
            if not job.end_time:
                job.end_time = datetime.now()

            # 获取 ODB 文件大小
            self._update_odb_size(job)

            if self.settings.VERBOSE:
                print(f"作业完成: {job.name} - {job.status.value}")

            # 从运行列表移除
            job_key = f"{job.name}@{job.work_dir}"
            self.running_jobs.pop(job_key, None)
            self.completed_jobs.append(job)

        except Exception as e:
            print(f"完成作业处理失败 {job.name}: {e}")

    def _handle_orphan_job(self, job: JobInfo, sta_file: Path):
        """
        处理孤立作业（进程停止但 .lck 未删除）

        Args:
            job: 作业信息
            sta_file: .sta 文件路径
        """
        try:
            # 计算耗时
            duration_str = "未知"
            if job.start_time:
                duration = datetime.now() - job.start_time
                hours, remainder = divmod(int(duration.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                duration_str = f"{hours}小时 {minutes}分钟 {seconds}秒"

            # 分析 .sta 文件状态
            status_str = StaParser.get_status_from_file(sta_file)
            job_info = get_job_info(sta_file)

            # 标记作业状态
            job.mark_completed(JobStatus.ABORTED, "Abaqus 进程已停止，但 .lck 文件仍存在")

            if self.settings.VERBOSE:
                print(f"作业异常终止: {job.name}")
                print(f"   Abaqus 进程已停止，但 .lck 文件仍存在")
                print(f"   运行时长: {duration_str}")

            # 发送孤立作业警告通知
            if self.webhook:
                self.webhook.send_orphan_job_warning(job, job_info, duration_str)

            # 获取 ODB 文件大小
            self._update_odb_size(job)

            # 添加到已完成列表
            job_key = f"{job.name}@{job.work_dir}"
            self.running_jobs.pop(job_key, None)
            self.completed_jobs.append(job)

        except Exception as e:
            print(f"处理孤立作业失败 {job.name}: {e}")

    def _update_odb_size(self, job: JobInfo):
        """更新 ODB 文件大小"""
        try:
            work_dir = Path(job.work_dir)
            odb_file = work_dir / f"{job.name}.odb"

            if odb_file.exists():
                size_mb = odb_file.stat().st_size / (1024 * 1024)
                job.odb_size_mb = round(size_mb, 2)

        except Exception:
            pass

    def _check_completed_jobs(self, directory: Path):
        """检查运行中的作业是否已完成"""
        completed_keys = []

        for job_key, job in self.running_jobs.items():
            # 检查 .lck 文件是否还存在
            lck_file = Path(job.work_dir) / f"{job.name}.lck"

            if not lck_file.exists():
                # .lck 文件不存在，作业完成
                sta_file = Path(job.work_dir) / f"{job.name}.sta"
                self._finalize_job(job, sta_file)
                completed_keys.append(job_key)

        # 清理已完成的作业
        for key in completed_keys:
            self.running_jobs.pop(key, None)

    def get_new_jobs(self, previously_known: Dict[str, JobInfo]) -> List[JobInfo]:
        """
        获取新检测到的作业

        Args:
            previously_known: 之前已知的作业 {job_key: JobInfo}

        Returns:
            新作业列表
        """
        new_jobs = []

        for job_key, job in self.running_jobs.items():
            if job_key not in previously_known:
                new_jobs.append(job)

        return new_jobs

    def get_running_jobs(self) -> List[JobInfo]:
        """获取当前运行中的作业"""
        return list(self.running_jobs.values())

    def is_job_running(self, job_name: str, work_dir: str) -> bool:
        """
        判断作业是否正在运行

        Args:
            job_name: 作业名称
            work_dir: 工作目录

        Returns:
            是否正在运行
        """
        job_key = f"{job_name}@{work_dir}"
        return job_key in self.running_jobs
