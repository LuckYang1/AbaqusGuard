"""
配置管理模块
从 TOML 加载配置，提供默认值
"""

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib

from src.models.job import JobInfo

_CONFIG_FILE_NAME = "config.toml"

_ALLOWED_WEBHOOK_EVENTS = {
    "start",
    "progress",
    "complete",
    "error",
    "orphan",
}

_ALLOWED_WEBHOOK_CHANNELS = {"feishu", "wecom"}


@dataclass
class WebhookRoute:
    """Webhook 路由规则"""

    channel: str
    webhook_url: str
    events: Set[str] = field(default_factory=set)
    match_dir: str = ""
    match_job: str = ""

    def matches(self, job: JobInfo, event: str) -> bool:
        """判断路由规则是否匹配"""
        if self.events and event not in self.events:
            return False

        if self.match_dir:
            work_dir = job.work_dir.replace("\\", "/")
            match_dir = self.match_dir.replace("\\", "/").rstrip("/")
            if not work_dir.startswith(match_dir + "/") and work_dir != match_dir:
                return False

        if self.match_job and not fnmatch.fnmatch(job.name, self.match_job):
            return False

        return True


@dataclass
class Settings:
    """应用配置"""

    # 飞书 Webhook 配置
    FEISHU_WEBHOOK_URL: str = ""

    # 企业微信 Webhook 配置
    WECOM_WEBHOOK_URL: str = ""

    # 多机器人路由配置
    WEBHOOK_ROUTES: List[WebhookRoute] = field(default_factory=list)

    # CSV 记录配置
    ENABLE_CSV_LOG: bool = True
    CSV_PATH: str = ""  # CSV 文件保存目录，留空使用项目根目录
    CSV_FILENAME: str = "abaqus_jobs_%Y%m.csv"  # 支持日期格式化和 {folder} 占位符
    CSV_UPDATE_INTERVAL: int = 60  # CSV 更新间隔（秒），设为 0 禁用定时更新
    CSV_OVERWRITE_MODE: str = "none"  # 覆盖模式: none/running/always
    CSV_MAX_HISTORY: int = 5  # 保留最近 N 条记录，0 表示不限制

    # Abaqus 监控配置
    WATCH_DIRS: Optional[List[str]] = None
    POLL_INTERVAL: int = 5
    VERBOSE: bool = True
    PROGRESS_NOTIFY_INTERVAL: int = 3600
    ENABLE_PROCESS_DETECTION: bool = True
    LCK_GRACE_PERIOD: int = 60
    JOB_END_CONFIRM_PERIOD: int = 60  # .lck 删除后的结束确认期（秒），0 表示禁用

    # 通知去重与进度阈值
    NOTIFY_DEDUPE_TTL: int = 3600  # 通知去重窗口（秒）
    PROGRESS_NOTIFY_MIN_TOTAL_TIME_DELTA: float = (
        0.0  # Total Time 最小增量阈值（<=0 表示不启用）
    )

    def __post_init__(self):
        """初始化后处理，转换类型和设置默认值"""
        if self.WATCH_DIRS is None:
            self.WATCH_DIRS = []
        else:
            self.WATCH_DIRS = [
                str(d).strip() for d in self.WATCH_DIRS if str(d).strip()
            ]

    @staticmethod
    def _parse_webhook_routes(routes: Any) -> List[WebhookRoute]:
        """解析 Webhook 路由配置"""
        if not isinstance(routes, list):
            return []

        parsed: List[WebhookRoute] = []
        for item in routes:
            if not isinstance(item, dict):
                continue

            channel = str(item.get("channel", "")).strip().lower()
            webhook_url = str(item.get("webhook_url", "")).strip()
            events = item.get("events", [])
            match_dir = str(item.get("match_dir", "")).strip()
            match_job = str(item.get("match_job", "")).strip()

            if channel not in _ALLOWED_WEBHOOK_CHANNELS:
                continue
            if not webhook_url:
                continue

            event_set: Set[str] = set()
            if isinstance(events, list):
                for event in events:
                    event_name = str(event).strip().lower()
                    if event_name in _ALLOWED_WEBHOOK_EVENTS:
                        event_set.add(event_name)

            parsed.append(
                WebhookRoute(
                    channel=channel,
                    webhook_url=webhook_url,
                    events=event_set,
                    match_dir=match_dir,
                    match_job=match_job,
                )
            )

        return parsed

    def select_webhook_urls(self, job: JobInfo, event: str, channel: str) -> List[str]:
        """获取匹配的 Webhook URL 列表"""
        event_name = event.strip().lower()
        channel_name = channel.strip().lower()
        if channel_name not in _ALLOWED_WEBHOOK_CHANNELS:
            return []
        if event_name not in _ALLOWED_WEBHOOK_EVENTS:
            return []

        matched = [
            route.webhook_url
            for route in self.WEBHOOK_ROUTES
            if route.channel == channel_name and route.matches(job, event_name)
        ]

        if matched:
            return matched

        default_url = (
            self.FEISHU_WEBHOOK_URL
            if channel_name == "feishu"
            else self.WECOM_WEBHOOK_URL
        )
        return [default_url] if default_url else []

    def reload(self) -> None:
        """从配置文件重新加载配置"""
        new_settings = Settings.load()
        self.__dict__.update(new_settings.__dict__)

    @classmethod
    def load(cls) -> "Settings":
        """从 TOML 配置文件加载配置"""
        config_path = _get_config_path()
        data = _load_toml_config(config_path)

        csv_config = _get_section(data, "csv")
        webhook_config = _get_section(data, "webhook")
        routes = webhook_config.get("routes", [])

        return cls(
            FEISHU_WEBHOOK_URL=_get_str(webhook_config, "feishu_url", ""),
            WECOM_WEBHOOK_URL=_get_str(webhook_config, "wecom_url", ""),
            WEBHOOK_ROUTES=cls._parse_webhook_routes(routes),
            ENABLE_CSV_LOG=_get_bool(csv_config, "enable", True),
            CSV_PATH=_get_str(csv_config, "path", ""),
            CSV_FILENAME=_get_str(csv_config, "filename", "abaqus_jobs_%Y%m.csv"),
            CSV_UPDATE_INTERVAL=_get_int(csv_config, "update_interval", 60),
            CSV_OVERWRITE_MODE=_get_str(csv_config, "overwrite_mode", "none"),
            CSV_MAX_HISTORY=_get_int(csv_config, "max_history", 5),
            WATCH_DIRS=_get_list(data.get("watch_dirs"), []),
            POLL_INTERVAL=_get_int(data, "poll_interval", 5),
            VERBOSE=_get_bool(data, "verbose", True),
            PROGRESS_NOTIFY_INTERVAL=_get_int(data, "progress_notify_interval", 3600),
            ENABLE_PROCESS_DETECTION=_get_bool(data, "enable_process_detection", True),
            LCK_GRACE_PERIOD=_get_int(data, "lck_grace_period", 60),
            JOB_END_CONFIRM_PERIOD=_get_int(data, "job_end_confirm_period", 60),
            NOTIFY_DEDUPE_TTL=_get_int(data, "notify_dedupe_ttl", 3600),
            PROGRESS_NOTIFY_MIN_TOTAL_TIME_DELTA=_get_float(
                data, "progress_notify_min_total_time_delta", 0.0
            ),
        )


def _get_config_path() -> Path:
    """获取配置文件路径"""
    return Path(__file__).resolve().parents[2] / _CONFIG_FILE_NAME


def _load_toml_config(path: Path) -> Dict[str, Any]:
    """加载 TOML 配置文件"""
    if not path.exists():
        print(f"未找到配置文件: {path}")
        return {}

    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"配置文件读取失败: {exc}")
        return {}


def _get_section(data: Dict[str, Any], key: str) -> Dict[str, Any]:
    """读取配置分组"""
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def _get_str(data: Dict[str, Any], key: str, default: str) -> str:
    """读取字符串配置"""
    value = data.get(key, default)
    return str(value) if value is not None else default


def _get_int(data: Dict[str, Any], key: str, default: int) -> int:
    """读取整数配置"""
    value = data.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_float(data: Dict[str, Any], key: str, default: float) -> float:
    """读取浮点数配置"""
    value = data.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_bool(data: Dict[str, Any], key: str, default: bool) -> bool:
    """读取布尔配置"""
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return default


def _get_list(value: Any, default: List[str]) -> List[str]:
    """读取字符串列表配置"""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return default


# 全局配置实例
settings = Settings.load()


def get_settings() -> Settings:
    """获取配置单例"""
    return settings
