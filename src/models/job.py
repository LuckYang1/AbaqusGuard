"""
作业数据模型
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class JobStatus(Enum):
    """作业状态枚举"""
    RUNNING = "运行中"
    SUCCESS = "成功"
    FAILED = "失败"
    ABORTED = "异常终止"


@dataclass
class JobInfo:
    """Abaqus 作业信息"""
    name: str                              # 作业名称
    work_dir: str                          # 工作目录
    computer: str                          # 计算机名
    start_time: datetime                   # 开始时间
    end_time: Optional[datetime] = None    # 结束时间
    status: JobStatus = JobStatus.RUNNING  # 状态
    result: str = ""                       # 计算结果描述
    odb_size_mb: float = 0.0               # ODB大小
    total_time: float = 0.0                # .sta中的Total Time
    frequency: float = 0.0                 # .sta中的Frequency
    step: int = 0                          # 当前Step
    increment: int = 0                     # 当前Increment

    # 飞书多维表格记录ID
    record_id: Optional[str] = None        # 多维表格记录ID

    @property
    def duration(self) -> Optional[str]:
        """计算耗时，返回格式化字符串"""
        if not self.end_time:
            return None
        delta = self.end_time - self.start_time
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}小时 {minutes}分钟 {seconds}秒"

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.status == JobStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        """是否已完成（成功或失败）"""
        return self.status in (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.ABORTED)

    def mark_completed(self, status: JobStatus, result: str = ""):
        """标记作业完成"""
        self.status = status
        self.end_time = datetime.now()
        if result:
            self.result = result
