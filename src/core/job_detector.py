"""
作业检测器
通过监控 .lck 文件检测 Abaqus 作业的开始和结束
"""
import socket
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.config.settings import get_settings
from src.core.progress_parser import StaParser
from src.core.process_detector import get_process_detector
from src.models.job import JobInfo, JobStatus


class JobDetector:
    """Abaqus 作业检测器"""

    def __init__(self):
        """初始化检测器"""
        self.settings = get_settings()
        self.process_detector = get_process_detector()
        self.running_jobs: Dict[str, JobInfo] = {}  # 正在运行的作业
        self.completed_jobs: List[JobInfo] = []      # 已完成的作业

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

                # 检查是否已完成
                if not lck_file.exists():
                    # .lck 文件被删除，作业可能完成
                    self._finalize_job(job, sta_file)
                    jobs.append(job)
            else:
                # 新作业
                job = self._create_new_job(job_name, directory, sta_file)
                if job:
                    self.running_jobs[job_key] = job
                    jobs.append(job)

        # 检查之前运行的作业是否已完成
        self._check_completed_jobs(directory)

        return jobs

    def _create_new_job(self, job_name: str, work_dir: Path, sta_file: Path) -> Optional[JobInfo]:
        """创建新作业信息"""
        try:
            # 检查作业进程是否正在运行
            if not self.process_detector.is_job_process_running(job_name):
                if self.settings.VERBOSE:
                    print(f"跳过孤立 .lck 文件: {job_name} @ {work_dir} (未检测到对应进程)")
                return None

            # 从 .sta 文件解析开始时间
            start_time = StaParser.extract_start_time(sta_file)
            if not start_time:
                start_time = datetime.now()

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
