"""
配置管理模块
从环境变量加载配置，提供默认值
"""
import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


@dataclass
class Settings:
    """应用配置"""

    # 飞书 Webhook 配置
    FEISHU_WEBHOOK_URL: str = ""

    # CSV 记录配置
    ENABLE_CSV_LOG: bool = True
    CSV_PATH: str = ""  # CSV 文件保存目录，留空使用项目根目录
    CSV_FILENAME: str = "abaqus_jobs_%Y%m.csv"  # 支持日期格式化和 {folder} 占位符

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
        self.VERBOSE = self._parse_bool(os.getenv("VERBOSE", "true"), self.VERBOSE)
        self.ENABLE_PROCESS_DETECTION = self._parse_bool(
            os.getenv("ENABLE_PROCESS_DETECTION", "true"), self.ENABLE_PROCESS_DETECTION
        )
        self.ENABLE_CSV_LOG = self._parse_bool(
            os.getenv("ENABLE_CSV_LOG", "true"), self.ENABLE_CSV_LOG
        )

        # 转换字符串
        self.CSV_PATH = os.getenv("CSV_PATH", self.CSV_PATH)
        self.CSV_FILENAME = os.getenv("CSV_FILENAME", self.CSV_FILENAME)

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
            FEISHU_WEBHOOK_URL=os.getenv("FEISHU_WEBHOOK_URL", ""),
            WATCH_DIRS=None,  # 在 __post_init__ 中处理
        )


# 全局配置实例
settings = Settings.load()


def get_settings() -> Settings:
    """获取配置单例"""
    return settings
