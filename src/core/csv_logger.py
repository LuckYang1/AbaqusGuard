"""
CSV 记录模块
负责将作业记录写入本地 CSV 文件
"""
import csv
import socket
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config.settings import get_settings
from src.models.job import JobInfo


class JobCSVLogger:
    """作业 CSV 记录器"""

    # CSV 列定义
    COLUMNS = [
        "作业名称", "工作目录", "计算机", "开始时间", "结束时间",
        "耗时", "进度", "状态", "计算结果", "ODB大小(MB)", "Total Time"
    ]

    def __init__(self, csv_path: str = "", filename: str = "abaqus_jobs.csv"):
        """
        初始化 CSV 记录器

        Args:
            csv_path: CSV 文件保存目录（留空则使用脚本目录）
            filename: CSV 文件名（支持日期格式化，如 %Y%m，支持 {folder} 占位符）
        """
        self.settings = get_settings()

        if csv_path:
            self.base_path = Path(csv_path)
        else:
            self.base_path = Path(__file__).parent.parent.parent  # 项目根目录

        self.filename_template = filename

    def _get_csv_path(self, directory: str = "") -> Path:
        """获取当前 CSV 文件路径（支持日期格式化和文件夹名）"""
        # 提取文件夹名
        folder_name = Path(directory).name if directory else "default"
        # 替换 {folder} 占位符并格式化日期
        filename = self.filename_template.replace("{folder}", folder_name)
        filename = datetime.now().strftime(filename)
        return self.base_path / filename

    def _ensure_csv_exists(self, csv_path: Path) -> None:
        """确保 CSV 文件存在，不存在则创建并写入表头"""
        if not csv_path.exists():
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(self.COLUMNS)
            self._log(f"创建 CSV 文件: {csv_path}")

    def _log(self, message: str):
        """输出日志"""
        if self.settings.VERBOSE:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] {message}")

    def add_job(self, job: JobInfo) -> bool:
        """
        添加作业记录（作业开始时调用）

        Args:
            job: 作业信息

        Returns:
            是否成功
        """
        try:
            csv_path = self._get_csv_path(job.work_dir)
            self._ensure_csv_exists(csv_path)

            row_data = {
                "作业名称": job.name,
                "工作目录": job.work_dir,
                "计算机": job.computer,
                "开始时间": job.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                "结束时间": "",
                "耗时": "",
                "进度": "0%",
                "状态": "运行中",
                "计算结果": "",
                "ODB大小(MB)": "",
                "Total Time": "",
            }

            # 写入 CSV
            with open(csv_path, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                writer.writerow(row_data)

            self._log(f"作业记录已添加到 CSV: {job.name}")
            return True

        except Exception as e:
            self._log(f"添加 CSV 记录失败: {e}")
            return False

    def update_job(self, job: JobInfo) -> bool:
        """
        更新作业记录（就地更新，不追加新行）

        Args:
            job: 作业信息

        Returns:
            是否成功
        """
        try:
            csv_path = self._get_csv_path(job.work_dir)
            if not csv_path.exists():
                self._log(f"CSV 文件不存在，无法更新: {csv_path}")
                return False

            # 读取所有行
            rows = []
            target_row_idx = -1

            with open(csv_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    rows.append(row)
                    # 找到匹配的作业记录（最后一条匹配的记录）
                    if row.get("作业名称") == job.name:
                        target_row_idx = idx

            if target_row_idx == -1:
                self._log(f"未找到作业记录: {job.name}")
                return False

            # 更新目标行
            status = job.status.value
            # 计算进度百分比
            progress = ""
            if job.total_step_time > 0:
                percent = min(job.total_time / job.total_step_time * 100, 100)
                progress = f"{percent:.1f}%"
            elif job.is_completed:
                progress = "100%"

            rows[target_row_idx].update({
                "结束时间": job.end_time.strftime('%Y-%m-%d %H:%M:%S') if job.end_time else "",
                "耗时": job.duration or "",
                "进度": progress,
                "状态": status,
                "计算结果": job.result,
                "ODB大小(MB)": f"{job.odb_size_mb:.2f}" if job.odb_size_mb else "",
                "Total Time": f"{job.total_time:.2f}" if job.total_time else "",
            })

            # 重新写入整个文件
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                writer.writeheader()
                writer.writerows(rows)

            self._log(f"作业记录已更新: {job.name} ({status})")
            return True

        except Exception as e:
            self._log(f"更新 CSV 记录失败: {e}")
            return False


# 全局 CSV 记录器实例
_logger: Optional[JobCSVLogger] = None


def get_csv_logger() -> Optional[JobCSVLogger]:
    """获取 CSV 记录器单例"""
    return _logger


def init_csv_logger(csv_path: str = "", filename_template: str = "abaqus_jobs.csv") -> JobCSVLogger:
    """
    初始化 CSV 记录器

    Args:
        csv_path: CSV 文件保存目录
        filename_template: CSV 文件名模板

    Returns:
        CSV 记录器实例
    """
    global _logger
    _logger = JobCSVLogger(csv_path, filename_template)
    return _logger
