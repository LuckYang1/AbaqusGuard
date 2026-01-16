"""
配置管理模块
从环境变量加载配置，提供默认值
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


@dataclass
class Settings:
    """应用配置"""

    # 飞书应用配置
    FEISHU_APP_ID: str
    FEISHU_APP_SECRET: str

    # 飞书 Webhook 配置
    FEISHU_WEBHOOK_URL: str = ""

    # 多维表格配置
    FEISHU_BITABLE_APP_TOKEN: str = ""
    FEISHU_TABLE_ID: str = ""
    FEISHU_TABLE_NAME: str = "Abaqus作业日志"
    ENABLE_FEISHU_BITABLE: bool = True
    AUTO_CREATE_TABLE: bool = True

    # 用户身份配置（用于创建用户拥有的表格）
    FEISHU_USER_ACCESS_TOKEN: str = ""  # 用户访问凭证，表格将属于该用户

    # Abaqus 监控配置
    WATCH_DIRS: List[str] = None
    POLL_INTERVAL: int = 5
    VERBOSE: bool = True
    PROGRESS_NOTIFY_INTERVAL: int = 3600
    ENABLE_PROCESS_DETECTION: bool = True
    LCK_GRACE_PERIOD: int = 60

    def __post_init__(self):
        """初始化后处理，转换类型和设置默认值"""
        if self.WATCH_DIRS is None:
            watch_dirs_str = os.getenv("WATCH_DIRS", "")
            self.WATCH_DIRS = [d.strip() for d in watch_dirs_str.split(",") if d.strip()]

        # 转换布尔值
        self.ENABLE_FEISHU_BITABLE = self._parse_bool(
            os.getenv("ENABLE_FEISHU_BITABLE", "true"), self.ENABLE_FEISHU_BITABLE
        )
        self.AUTO_CREATE_TABLE = self._parse_bool(
            os.getenv("AUTO_CREATE_TABLE", "true"), self.AUTO_CREATE_TABLE
        )
        self.VERBOSE = self._parse_bool(os.getenv("VERBOSE", "true"), self.VERBOSE)
        self.ENABLE_PROCESS_DETECTION = self._parse_bool(
            os.getenv("ENABLE_PROCESS_DETECTION", "true"), self.ENABLE_PROCESS_DETECTION
        )

        # 转换整数
        self.POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", str(self.POLL_INTERVAL)))
        self.PROGRESS_NOTIFY_INTERVAL = int(
            os.getenv("PROGRESS_NOTIFY_INTERVAL", str(self.PROGRESS_NOTIFY_INTERVAL))
        )
        self.LCK_GRACE_PERIOD = int(os.getenv("LCK_GRACE_PERIOD", str(self.LCK_GRACE_PERIOD)))

    @staticmethod
    def _parse_bool(value: str, default: bool) -> bool:
        """解析布尔值字符串"""
        if isinstance(value, bool):
            return value
        return value.lower() in ("true", "1", "yes", "on") if value else default

    @classmethod
    def load(cls) -> "Settings":
        """从环境变量加载配置"""
        return cls(
            FEISHU_APP_ID=os.getenv("FEISHU_APP_ID", ""),
            FEISHU_APP_SECRET=os.getenv("FEISHU_APP_SECRET", ""),
            FEISHU_WEBHOOK_URL=os.getenv("FEISHU_WEBHOOK_URL", ""),
            FEISHU_BITABLE_APP_TOKEN=os.getenv("FEISHU_BITABLE_APP_TOKEN", ""),
            FEISHU_TABLE_ID=os.getenv("FEISHU_TABLE_ID", ""),
            FEISHU_TABLE_NAME=os.getenv("FEISHU_TABLE_NAME", "Abaqus作业日志"),
            FEISHU_USER_ACCESS_TOKEN=os.getenv("FEISHU_USER_ACCESS_TOKEN", ""),
            WATCH_DIRS=None,  # 在 __post_init__ 中处理
        )


# 全局配置实例
settings = Settings.load()


def get_settings() -> Settings:
    """获取配置单例"""
    return settings
