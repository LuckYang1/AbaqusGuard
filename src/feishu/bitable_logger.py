"""
飞书多维表格记录模块
负责将作业记录同步到飞书多维表格
仿照 csv_logger.py 的设计，提供相同的接口
"""

from datetime import datetime
from typing import Dict, Any, Optional

from src.feishu.bitable_client import BitableClient
from src.models.job import JobInfo


class BitableLogger:
    """飞书多维表格记录器"""

    # 字段名称定义（与多维表格表头保持一致）
    FIELD_NAMES = {
        "job_name": "作业名称",
        "work_dir": "工作目录",
        "computer": "计算机",
        "start_time": "开始时间",
        "end_time": "结束时间",
        "duration": "耗时",
        "progress": "进度",
        "status": "状态",
        "result": "计算结果",
        "odb_size": "ODB大小(MB)",
        "total_time": "Total Time",
        # "update_time": "更新时间",  # 暂时注释掉，需要在多维表格中添加此字段
    }

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str,
        verbose: bool = False,
        max_history: int = 5,
    ):
        """
        初始化多维表格记录器

        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用 Secret
            app_token: 多维表格 token
            table_id: 数据表 ID
            verbose: 是否输出详细日志
            max_history: 保留历史记录数（每个作业），0 表示不限制
        """
        self.client = BitableClient(app_id, app_secret, verbose)
        self.app_token = app_token
        self.table_id = table_id
        self.verbose = verbose
        self.max_history = max_history
        self._job_record_map: Dict[str, str] = {}  # {job_key: record_id}

    def _log(self, message: str):
        """输出日志"""
        if self.verbose:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] [BitableLogger] {message}")

    def _get_job_key(self, job: JobInfo) -> str:
        """
        生成作业唯一标识键

        Args:
            job: 作业信息

        Returns:
            唯一键（作业名称 + 工作目录 + 开始时间）
        """
        start_time_str = job.start_time.strftime("%Y-%m-%d %H:%M:%S")
        return f"{job.name}|{job.work_dir}|{start_time_str}"

    def _cleanup_old_records(self, job: JobInfo, keep: int) -> None:
        """
        清理旧记录，保留最近 N 条

        Args:
            job: 作业信息
            keep: 保留数量
        """
        if keep <= 0:
            return

        try:
            # 查询所有匹配的记录（作业名称 + 工作目录）
            filter_str = f'([{self.FIELD_NAMES["job_name"]}]="{job.name}" AND [{self.FIELD_NAMES["work_dir"]}]="{job.work_dir}")'

            records = self.client.search_records(
                app_token=self.app_token,
                table_id=self.table_id,
                filter_str=filter_str,
                field_names=[self.FIELD_NAMES["start_time"]],
            )

            if not records:
                return

            # 按开始时间降序排序，取最新的
            sorted_records = sorted(
                records,
                key=lambda r: r.get("fields", {}).get(
                    self.FIELD_NAMES["start_time"], 0
                ),
                reverse=True,
            )

            # 如果匹配数量超过保留数量，删除最早的
            if len(sorted_records) > keep:
                # 要删除的记录（跳过最后 keep 条）
                records_to_delete = sorted_records[keep:]

                deleted_count = 0
                for record in records_to_delete:
                    record_id = record.get("record_id")
                    if record_id:
                        success = self.client.delete_record(
                            app_token=self.app_token,
                            table_id=self.table_id,
                            record_id=record_id,
                        )
                        if success:
                            deleted_count += 1
                            # 清理缓存中的映射
                            for key, value in list(self._job_record_map.items()):
                                if value == record_id:
                                    del self._job_record_map[key]

                if deleted_count > 0:
                    self._log(f"清理旧记录: {job.name}，删除 {deleted_count} 条")

        except Exception as e:
            self._log(f"清理旧记录失败: {job.name}, {e}")

    def _build_fields(self, job: JobInfo, is_new: bool = True) -> Dict[str, Any]:
        """
        构建多维表格字段数据

        Args:
            job: 作业信息
            is_new: 是否为新记录

        Returns:
            字段字典
        """
        if is_new:
            # 新记录（作业开始时）
            return {
                self.FIELD_NAMES["job_name"]: job.name,
                self.FIELD_NAMES["work_dir"]: job.work_dir,
                self.FIELD_NAMES["computer"]: job.computer,
                self.FIELD_NAMES["start_time"]: int(job.start_time.timestamp() * 1000),
                self.FIELD_NAMES["end_time"]: None,
                self.FIELD_NAMES["duration"]: "",
                self.FIELD_NAMES[
                    "progress"
                ]: 0.0,  # 进度类型字段（小数：0-1 表示 0%-100%）
                self.FIELD_NAMES["status"]: "运行中",
                self.FIELD_NAMES["result"]: "",
                self.FIELD_NAMES["odb_size"]: 0,
                self.FIELD_NAMES["total_time"]: 0,
                # self.FIELD_NAMES["update_time"]: int(datetime.now().timestamp() * 1000),  # 暂时注释
            }
        else:
            # 更新记录（作业进度更新或完成时）
            # 计算进度百分比（转换为小数：0-1）
            progress_percent = 0.0
            if job.total_step_time > 0:
                progress_percent = min(job.total_time / job.total_step_time, 1.0)
            elif job.is_completed:
                progress_percent = 1.0

            return {
                self.FIELD_NAMES["end_time"]: int(job.end_time.timestamp() * 1000)
                if job.end_time
                else None,
                self.FIELD_NAMES["duration"]: job.duration or "",
                self.FIELD_NAMES["progress"]: progress_percent,
                self.FIELD_NAMES["status"]: job.status.value,
                self.FIELD_NAMES["result"]: job.result or "",
                self.FIELD_NAMES["odb_size"]: round(job.odb_size_mb, 2)
                if job.odb_size_mb
                else 0,
                self.FIELD_NAMES["total_time"]: round(job.total_time, 2)
                if job.total_time
                else 0,
                # self.FIELD_NAMES["update_time"]: int(datetime.now().timestamp() * 1000),  # 暂时注释
            }

    def _search_existing_record(self, job: JobInfo) -> Optional[str]:
        """
        查询现有记录

        Args:
            job: 作业信息

        Returns:
            记录 ID，未找到返回 None
        """
        # 构建过滤条件：作业名称 + 工作目录
        # 注意：过滤条件需要用公式语法
        filter_str = f'([{self.FIELD_NAMES["job_name"]}]="{job.name}" AND [{self.FIELD_NAMES["work_dir"]}]="{job.work_dir}")'

        records = self.client.search_records(
            app_token=self.app_token,
            table_id=self.table_id,
            filter_str=filter_str,
            field_names=list(self.FIELD_NAMES.values()),
        )

        if not records:
            return None

        # 按开始时间降序排序，取最新的
        sorted_records = sorted(
            records,
            key=lambda r: r.get("fields", {}).get(self.FIELD_NAMES["start_time"], 0),
            reverse=True,
        )

        return sorted_records[0].get("record_id")

    def add_job(self, job: JobInfo) -> bool:
        """
        添加作业记录（作业开始时调用）

        Args:
            job: 作业信息

        Returns:
            是否成功
        """
        try:
            job_key = self._get_job_key(job)

            # 检查缓存中是否已存在该作业的记录
            if job_key in self._job_record_map:
                self._log(f"作业记录已存在，跳过添加: {job.name}")
                return True

            fields = self._build_fields(job, is_new=True)

            # 创建新记录
            record_id = self.client.create_record(
                app_token=self.app_token, table_id=self.table_id, fields=fields
            )

            if record_id:
                # 保存记录 ID 映射
                self._job_record_map[job_key] = record_id
                self._log(
                    f"作业记录已添加到多维表格: {job.name} (record_id={record_id})"
                )

                # 添加记录后清理旧记录
                if self.max_history > 0:
                    self._cleanup_old_records(job, self.max_history)

                return True
            else:
                return False

        except Exception as e:
            self._log(f"添加多维表格记录失败: {job.name}, {e}")
            return False

    def update_job(self, job: JobInfo) -> bool:
        """
        更新作业记录（作业进度更新或完成时调用）
        作业完成时，根据 max_history 配置清理旧记录

        Args:
            job: 作业信息

        Returns:
            是否成功
        """
        try:
            job_key = self._get_job_key(job)

            # 优先使用缓存的 record_id
            record_id = self._job_record_map.get(job_key)

            # 如果缓存中没有，查询现有记录
            if not record_id:
                record_id = self._search_existing_record(job)

            if not record_id:
                # 未找到记录，自动新增
                self._log(f"未找到作业记录: {job.name}，自动新增")
                fields = self._build_fields(job, is_new=True)
                # 用更新数据覆盖初始数据
                update_fields = self._build_fields(job, is_new=False)
                fields.update(update_fields)

                record_id = self.client.create_record(
                    app_token=self.app_token, table_id=self.table_id, fields=fields
                )

                if record_id:
                    self._job_record_map[job_key] = record_id
                    self._log(f"作业记录已自动添加: {job.name} (record_id={record_id})")

                    # 如果作业已完成，执行历史清理
                    if job.is_completed and self.max_history > 0:
                        self._cleanup_old_records(job, self.max_history)
                    return True
                else:
                    return False

            # 构建更新字段
            fields = self._build_fields(job, is_new=False)

            # 更新记录
            success = self.client.update_record(
                app_token=self.app_token,
                table_id=self.table_id,
                record_id=record_id,
                fields=fields,
            )

            if success:
                self._log(f"作业记录已更新: {job.name} ({job.status.value})")

                # 如果作业已完成，执行历史清理
                if job.is_completed and self.max_history > 0:
                    self._cleanup_old_records(job, self.max_history)
            else:
                # 更新失败（可能记录已被删除），清除缓存并尝试新增
                if job_key in self._job_record_map:
                    del self._job_record_map[job_key]

                self._log(f"更新失败，尝试新增记录: {job.name}")
                fields = self._build_fields(job, is_new=True)
                update_fields = self._build_fields(job, is_new=False)
                fields.update(update_fields)

                new_record_id = self.client.create_record(
                    app_token=self.app_token, table_id=self.table_id, fields=fields
                )

                if new_record_id:
                    self._job_record_map[job_key] = new_record_id
                    self._log(f"作业记录已自动添加: {job.name} (record_id={new_record_id})")

                    if job.is_completed and self.max_history > 0:
                        self._cleanup_old_records(job, self.max_history)
                    return True
                else:
                    return False

            return success

        except Exception as e:
            self._log(f"更新多维表格记录失败: {job.name}, {e}")
            return False


# 全局多维表格记录器实例
_logger: Optional[BitableLogger] = None


def get_bitable_logger() -> Optional[BitableLogger]:
    """获取多维表格记录器单例"""
    return _logger


def init_bitable_logger(
    app_id: str,
    app_secret: str,
    app_token: str,
    table_id: str,
    verbose: bool = False,
    max_history: int = 5,
) -> BitableLogger:
    """
    初始化多维表格记录器

    Args:
        app_id: 飞书应用 ID
        app_secret: 飞书应用 Secret
        app_token: 多维表格 token
        table_id: 数据表 ID
        verbose: 是否输出详细日志
        max_history: 保留历史记录数（每个作业），0 表示不限制

    Returns:
        多维表格记录器实例
    """
    global _logger
    _logger = BitableLogger(
        app_id, app_secret, app_token, table_id, verbose, max_history
    )
    return _logger
