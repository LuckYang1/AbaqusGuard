"""
作业检测器
通过监控 .lck 文件检测 Abaqus 作业的开始和结束
参考 abaqus-monitoring 项目使用集合运算处理作业状态
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
        # {目录: {作业名: JobInfo}}
        self.running_jobs: Dict[Path, Dict[str, JobInfo]] = {}
        self.completed_jobs: List[JobInfo] = []
        # {目录: 已知的孤立 .lck 文件集合}
        self.ignored_lck: Dict[Path, Set[str]] = {}

    def scan_directories(self) -> List[JobInfo]:
        """
        扫描所有监控目录，检测作业状态

        Returns:
            所有检测到的作业列表（包括运行中和已完成）
        """
        all_jobs = []

        for watch_dir in self.settings.WATCH_DIRS:
            watch_path = Path(watch_dir)
            # 初始化该目录的数据结构
            if watch_path not in self.running_jobs:
                self.running_jobs[watch_path] = {}
            if watch_path not in self.ignored_lck:
                self.ignored_lck[watch_path] = set()

            jobs = self._scan_directory(watch_path)
            all_jobs.extend(jobs)

        return all_jobs

    def _scan_directory(self, directory: Path) -> List[JobInfo]:
        """
        扫描单个目录 - 使用集合运算处理作业状态

        核心逻辑（参考 abaqus-monitoring）:
        - current_lck: 当前扫描到的所有 .lck 文件
        - previous_jobs: 之前活跃的作业集合
        - effective_lck: 当前有效的 .lck (排除已知的孤立文件)
        - new_lck: 新的作业 = effective_lck - previous_jobs
        - ended_jobs: 结束的作业 = previous_jobs - current_lck
        - active_jobs_now: 仍然活跃 = previous_jobs & effective_lck
        """
        jobs = []

        if not directory.exists():
            if self.settings.VERBOSE:
                print(f"目录不存在: {directory}")
            return jobs

        # 1. 获取当前所有 .lck 文件
        current_lck = self._scan_lck_files(directory)

        # 2. 获取之前活跃的作业
        previous_jobs = set(self.running_jobs[directory].keys())

        # 3. 清理已删除的孤立 .lck 文件
        removed_ignored = self.ignored_lck[directory] - current_lck
        if removed_ignored and self.settings.VERBOSE:
            for job_name in removed_ignored:
                print(f"孤立 .lck 文件已被清理: {job_name}")
        self.ignored_lck[directory] -= removed_ignored

        # 4. 检查 Abaqus 进程状态（只检测一次）
        abaqus_running = True
        if self.settings.ENABLE_PROCESS_DETECTION:
            abaqus_running = self.process_detector.is_abaqus_running()

        # 5. 计算有效的 .lck 文件（排除已知孤立的）
        effective_lck = current_lck - self.ignored_lck[directory]

        # 6. 处理新作业 = 有效的 - 之前的
        new_lck = effective_lck - previous_jobs
        for job_name in new_lck:
            job = self._handle_new_job(directory, job_name, abaqus_running)
            if job:
                jobs.append(job)

        # 7. 处理结束的作业 = 之前的 - 当前的
        ended_jobs = previous_jobs - current_lck
        for job_name in ended_jobs:
            job = self.running_jobs[directory].pop(job_name)
            self._handle_job_end(job, directory)
            jobs.append(job)

        # 8. 计算仍然活跃的作业 = 之前的 & 有效的
        active_jobs_now = previous_jobs & effective_lck

        # 9. 检查活跃作业是否变成孤立（进程停止但 .lck 未删除）
        active_jobs_after_orphan_check = set()
        if self.settings.ENABLE_PROCESS_DETECTION and active_jobs_now and not abaqus_running:
            for job_name in list(active_jobs_now):
                lck_age = self._get_lck_age(directory, job_name)
                if lck_age < self.settings.LCK_GRACE_PERIOD:
                    # 在宽限期内，继续监控
                    active_jobs_after_orphan_check.add(job_name)
                else:
                    # 超过宽限期且无进程，判定为孤立
                    job = self.running_jobs[directory].pop(job_name)
                    self._handle_orphan_job(job, directory)
                    # 加入孤立列表，避免重复处理
                    self.ignored_lck[directory].add(job_name)
                    jobs.append(job)
        else:
            active_jobs_after_orphan_check = active_jobs_now

        # 10. 更新活跃作业的进度
        for job_name in active_jobs_after_orphan_check:
            job = self.running_jobs[directory][job_name]
            self._update_job_progress(job, directory)
            jobs.append(job)

        return jobs

    def _scan_lck_files(self, directory: Path) -> Set[str]:
        """
        扫描目录下的所有 .lck 文件

        Returns:
            .lck 文件名集合（不含扩展名）
        """
        lck_files = set()
        try:
            for item in directory.iterdir():
                if item.suffix.lower() == '.lck' and item.is_file():
                    lck_files.add(item.stem)
        except PermissionError:
            print(f"无权限访问目录: {directory}")
        except Exception as e:
            print(f"扫描目录出错 {directory}: {e}")
        return lck_files

    def _handle_new_job(self, directory: Path, job_name: str, abaqus_running: bool) -> Optional[JobInfo]:
        """
        处理新作业

        Args:
            directory: 目录路径
            job_name: 作业名称
            abaqus_running: Abaqus 进程是否在运行

        Returns:
            创建的作业对象，失败返回 None
        """
        lck_file = directory / f"{job_name}.lck"

        # 检查是否应该作为新作业处理
        if self.settings.ENABLE_PROCESS_DETECTION and not abaqus_running:
            lck_age = self._get_lck_age(directory, job_name)
            if lck_age >= self.settings.LCK_GRACE_PERIOD:
                # 超过宽限期，判定为孤立文件
                if self.settings.VERBOSE:
                    print(f"检测到孤立 .lck 文件 (已存在 {int(lck_age)} 秒): {job_name}")
                self.ignored_lck[directory].add(job_name)
                return None
            else:
                # 在宽限期内，假设是新作业（进程可能还在启动）
                if self.settings.VERBOSE:
                    print(f"新 .lck 文件 ({int(lck_age)}秒)，等待进程启动: {job_name}")

        # 使用 .lck 文件的创建时间作为作业开始时间
        start_time = datetime.fromtimestamp(lck_file.stat().st_ctime)

        job = JobInfo(
            name=job_name,
            work_dir=str(directory),
            computer=socket.gethostname(),
            start_time=start_time,
            status=JobStatus.RUNNING,
        )

        # 解析初始进度
        self._update_job_progress(job, directory)

        # 添加到活跃作业
        self.running_jobs[directory][job_name] = job

        if self.settings.VERBOSE:
            print(f"作业开始: {job_name} @ {directory}")

        return job

    def _handle_job_end(self, job: JobInfo, directory: Path):
        """
        处理作业结束（.lck 文件被删除）

        Args:
            job: 作业对象
            directory: 目录路径
        """
        sta_file = directory / f"{job.name}.sta"

        # 分析 .sta 文件状态
        status_str = StaParser.get_status_from_file(sta_file)

        if status_str == "success":
            job.mark_completed(JobStatus.SUCCESS, "计算成功完成 - 收敛正常，结果可用")
        elif status_str == "failed":
            job.mark_completed(JobStatus.FAILED, "计算失败 - 分析未完成")
        else:
            job.mark_completed(JobStatus.ABORTED, "作业异常终止 - 状态未知")

        # 获取 ODB 文件大小
        self._update_odb_size(job, directory)

        if self.settings.VERBOSE:
            print(f"作业完成: {job.name} - {job.status.value}")

        # 添加到已完成列表
        self.completed_jobs.append(job)

    def _handle_orphan_job(self, job: JobInfo, directory: Path):
        """
        处理孤立作业（进程停止但 .lck 未删除）

        Args:
            job: 作业对象
            directory: 目录路径
        """
        sta_file = directory / f"{job.name}.sta"

        # 计算耗时
        duration_str = "未知"
        if job.start_time:
            duration = datetime.now() - job.start_time
            hours, remainder = divmod(int(duration.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = f"{hours}小时 {minutes}分钟 {seconds}秒"

        # 分析 .sta 文件状态
        job_info = get_job_info(sta_file)

        # 标记作业状态
        job.is_orphan = True  # 标记为孤立作业
        job.mark_completed(JobStatus.ABORTED, "Abaqus 进程已停止，但 .lck 文件仍存在")

        # 获取 ODB 文件大小
        self._update_odb_size(job, directory)

        if self.settings.VERBOSE:
            print(f"作业异常终止: {job.name}")
            print(f"   Abaqus 进程已停止，但 .lck 文件仍存在")
            print(f"   运行时长: {duration_str}")

        # 发送孤立作业警告通知
        if self.webhook:
            self.webhook.send_orphan_job_warning(job, job_info, duration_str)

        # 添加到已完成列表
        self.completed_jobs.append(job)

    def _update_job_progress(self, job: JobInfo, directory: Path):
        """更新作业进度"""
        try:
            sta_file = directory / f"{job.name}.sta"
            result = StaParser(sta_file).parse()
            job.step = result.get("step", 0)
            job.increment = result.get("increment", 0)
            job.total_time = result.get("total_time", 0.0)
            job.step_time = result.get("step_time", 0.0)
            job.inc_time = result.get("inc_time", 0.0)
        except Exception as e:
            if self.settings.VERBOSE:
                print(f"更新作业进度失败 {job.name}: {e}")

    def _get_lck_age(self, directory: Path, job_name: str) -> float:
        """
        获取 .lck 文件的年龄（自创建以来的秒数）

        Returns:
            .lck 文件存在的秒数，如果文件不存在则返回 0
        """
        lck_path = directory / f"{job_name}.lck"
        if lck_path.exists():
            create_time = lck_path.stat().st_ctime
            return time.time() - create_time
        return 0

    def _update_odb_size(self, job: JobInfo, directory: Path):
        """更新 ODB 文件大小"""
        try:
            odb_file = directory / f"{job.name}.odb"
            if odb_file.exists():
                size_mb = odb_file.stat().st_size / (1024 * 1024)
                job.odb_size_mb = round(size_mb, 2)
        except Exception:
            pass

    # ============ 兼容旧接口的方法 ============

    def get_new_jobs(self, previously_known: Dict[str, JobInfo]) -> List[JobInfo]:
        """
        获取新检测到的作业（兼容旧接口）

        Args:
            previously_known: 之前已知的作业 {job_key: JobInfo}

        Returns:
            新作业列表
        """
        new_jobs = []
        current_keys = set()

        # 构建当前所有作业的 key 集合
        for directory, jobs in self.running_jobs.items():
            for job_name, job in jobs.items():
                job_key = f"{job_name}@{directory}"
                current_keys.add(job_key)
                if job_key not in previously_known:
                    new_jobs.append(job)

        # 检查之前已知但现在已完成的作业
        for job_key in previously_known:
            if job_key not in current_keys:
                # 作业已完成，从 previously_known 移除
                pass

        return new_jobs

    def get_running_jobs(self) -> List[JobInfo]:
        """获取当前运行中的作业"""
        jobs = []
        for directory_jobs in self.running_jobs.values():
            jobs.extend(directory_jobs.values())
        return jobs

    def is_job_running(self, job_name: str, work_dir: str) -> bool:
        """
        判断作业是否正在运行（兼容旧接口）

        Args:
            job_name: 作业名称
            work_dir: 工作目录

        Returns:
            是否正在运行
        """
        directory = Path(work_dir)
        if directory in self.running_jobs:
            return job_name in self.running_jobs[directory]
        return False
