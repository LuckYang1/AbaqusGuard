"""
CSV 记录模块
负责将作业记录写入本地 CSV 文件
支持覆盖模式和历史记录清理
"""

import csv
import socket
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.config.settings import get_settings
from src.models.job import JobInfo


class JobCSVLogger:
    """作业 CSV 记录器"""

    # CSV 列定义
    COLUMNS = [
        "作业名称",
        "工作目录",
        "计算机",
        "开始时间",
        "结束时间",
        "耗时",
        "进度",
        "状态",
        "计算结果",
        "ODB大小(MB)",
        "Total Time",
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
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(self.COLUMNS)
            self._log(f"创建 CSV 文件: {csv_path}")

    def _log(self, message: str):
        """输出日志"""
        if self.settings.VERBOSE:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] {message}")

    def _read_all_rows(self, csv_path: Path) -> List[dict]:
        """读取 CSV 文件所有行"""
        rows = []
        if csv_path.exists():
            with open(csv_path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
        return rows

    def _write_all_rows(self, csv_path: Path, rows: List[dict]) -> None:
        """写入所有行到 CSV 文件"""
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def _find_matching_row(
        self,
        rows: List[dict],
        job_name: str,
        work_dir: str,
        status: Optional[str] = None,
    ) -> int:
        """
        查找匹配的记录索引（返回最后一条匹配的）

        Args:
            rows: 所有行数据
            job_name: 作业名称
            work_dir: 工作目录
            status: 可选，限定状态（如"运行中"）

        Returns:
            匹配的最后一条记录索引，未找到返回 -1
        """
        target_idx = -1
        for idx, row in enumerate(rows):
            if row.get("作业名称") == job_name and row.get("工作目录") == work_dir:
                if status is None or row.get("状态") == status:
                    target_idx = idx
        return target_idx

    def _cleanup_old_records(
        self, rows: List[dict], job_name: str, work_dir: str, keep: int
    ) -> List[dict]:
        """
        清理旧记录，保留最近 N 条

        Args:
            rows: 所有行数据
            job_name: 作业名称
            work_dir: 工作目录
            keep: 保留数量

        Returns:
            清理后的行列表
        """
        if keep <= 0:
            return rows

        # 找出所有匹配的记录索引
        matching_indices = []
        for idx, row in enumerate(rows):
            if row.get("作业名称") == job_name and row.get("工作目录") == work_dir:
                matching_indices.append(idx)

        # 如果匹配数量超过保留数量，删除最早的
        if len(matching_indices) > keep:
            # 要删除的索引（保留最后 keep 条）
            indices_to_remove = set(matching_indices[:-keep])
            rows = [row for idx, row in enumerate(rows) if idx not in indices_to_remove]
            self._log(f"清理旧记录: {job_name}，删除 {len(indices_to_remove)} 条")

        return rows

    def _build_row_data(self, job: JobInfo, is_new: bool = True) -> dict:
        """
        构建行数据

        Args:
            job: 作业信息
            is_new: 是否为新记录

        Returns:
            行数据字典
        """
        if is_new:
            return {
                "作业名称": job.name,
                "工作目录": job.work_dir,
                "计算机": job.computer,
                "开始时间": job.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "结束时间": "",
                "耗时": "",
                "进度": "0%",
                "状态": "运行中",
                "计算结果": "",
                "ODB大小(MB)": "",
                "Total Time": "",
            }
        else:
            # 计算进度百分比
            progress = ""
            if job.total_step_time > 0:
                percent = min(job.total_time / job.total_step_time * 100, 100)
                progress = f"{percent:.1f}%"
            elif job.is_completed:
                progress = "100%"

            return {
                "作业名称": job.name,
                "工作目录": job.work_dir,
                "计算机": job.computer,
                "开始时间": job.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "结束时间": job.end_time.strftime("%Y-%m-%d %H:%M:%S")
                if job.end_time
                else "",
                "耗时": job.duration or "",
                "进度": progress,
                "状态": job.status.value,
                "计算结果": job.result or "",
                "ODB大小(MB)": f"{job.odb_size_mb:.2f}" if job.odb_size_mb else "",
                "Total Time": f"{job.total_time:.2f}" if job.total_time else "",
            }

    def add_job(self, job: JobInfo) -> bool:
        """
        添加作业记录（作业开始时调用）

        根据 CSV_OVERWRITE_MODE 配置决定行为：
        - none: 总是新增记录
        - running: 覆盖同名且状态为"运行中"的记录
        - always: 总是覆盖同名的最后一条记录

        Args:
            job: 作业信息

        Returns:
            是否成功
        """
        try:
            csv_path = self._get_csv_path(job.work_dir)
            self._ensure_csv_exists(csv_path)

            mode = self.settings.CSV_OVERWRITE_MODE
            row_data = self._build_row_data(job, is_new=True)

            if mode == "none":
                # 直接追加新行
                with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                    writer.writerow(row_data)
                self._log(f"作业记录已添加到 CSV: {job.name}")

            elif mode == "running":
                # 查找同名+同目录+状态为"运行中"的记录
                rows = self._read_all_rows(csv_path)
                existing_idx = self._find_matching_row(
                    rows, job.name, job.work_dir, status="运行中"
                )

                if existing_idx >= 0:
                    # 覆盖现有记录
                    rows[existing_idx] = row_data
                    self._write_all_rows(csv_path, rows)
                    self._log(f"作业记录已覆盖（running模式）: {job.name}")
                else:
                    # 新增记录
                    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
                        writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                        writer.writerow(row_data)
                    self._log(f"作业记录已添加到 CSV: {job.name}")

            elif mode == "always":
                # 查找同名+同目录的最后一条记录
                rows = self._read_all_rows(csv_path)
                existing_idx = self._find_matching_row(rows, job.name, job.work_dir)

                if existing_idx >= 0:
                    # 覆盖现有记录
                    rows[existing_idx] = row_data
                    self._write_all_rows(csv_path, rows)
                    self._log(f"作业记录已覆盖（always模式）: {job.name}")
                else:
                    # 新增记录
                    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
                        writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                        writer.writerow(row_data)
                    self._log(f"作业记录已添加到 CSV: {job.name}")

            else:
                # 未知模式，使用默认行为（新增）
                with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
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

        使用 作业名称 + 工作目录 + 开始时间 精确匹配记录
        作业完成时，根据 CSV_MAX_HISTORY 配置清理旧记录

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
            rows = self._read_all_rows(csv_path)
            target_row_idx = -1
            start_time_str = job.start_time.strftime("%Y-%m-%d %H:%M:%S")

            # 精确匹配：作业名称 + 工作目录 + 开始时间
            for idx, row in enumerate(rows):
                if (
                    row.get("作业名称") == job.name
                    and row.get("工作目录") == job.work_dir
                    and row.get("开始时间") == start_time_str
                ):
                    target_row_idx = idx
                    break

            # 如果精确匹配失败，回退到 作业名称 + 工作目录（最后一条）
            if target_row_idx == -1:
                target_row_idx = self._find_matching_row(rows, job.name, job.work_dir)

            if target_row_idx == -1:
                self._log(f"未找到作业记录: {job.name}")
                return False

            # 更新目标行
            row_data = self._build_row_data(job, is_new=False)
            rows[target_row_idx].update(row_data)

            # 如果作业已完成，执行历史清理
            if job.is_completed and self.settings.CSV_MAX_HISTORY > 0:
                rows = self._cleanup_old_records(
                    rows, job.name, job.work_dir, self.settings.CSV_MAX_HISTORY
                )

            # 重新写入整个文件
            self._write_all_rows(csv_path, rows)

            self._log(f"作业记录已更新: {job.name} ({job.status.value})")
            return True

        except Exception as e:
            self._log(f"更新 CSV 记录失败: {e}")
            return False


# 全局 CSV 记录器实例
_logger: Optional[JobCSVLogger] = None


def get_csv_logger() -> Optional[JobCSVLogger]:
    """获取 CSV 记录器单例"""
    return _logger


def init_csv_logger(
    csv_path: str = "", filename_template: str = "abaqus_jobs.csv"
) -> JobCSVLogger:
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
