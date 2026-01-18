"""通知去重器

用于避免同一事件在短时间内重复发送（例如：轮询抖动、重启后重复上报、发送重试等）。
实现要求：
- 内存级别、无外部依赖
- 支持 TTL（过期自动清理）
- key 由调用方提供（稳定幂等键）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class NotificationDeduper:
    """基于 TTL 的通知去重器"""

    ttl_seconds: int = 3600
    _seen: Dict[str, float] = field(default_factory=dict)

    def should_send(self, key: str) -> bool:
        """判断某个幂等键是否应发送，并在允许发送时记录该 key

        Args:
            key: 幂等键

        Returns:
            True 表示允许发送；False 表示应跳过（重复）
        """
        if not key:
            # 没有 key 时不做去重
            return True

        now = time.time()
        self._cleanup(now)

        last = self._seen.get(key)
        if last is not None and (now - last) < self.ttl_seconds:
            return False

        self._seen[key] = now
        return True

    def _cleanup(self, now: float) -> None:
        """清理过期 key"""
        if self.ttl_seconds <= 0:
            self._seen.clear()
            return

        expire_before = now - self.ttl_seconds
        expired = [k for k, t in self._seen.items() if t < expire_before]
        for k in expired:
            self._seen.pop(k, None)


_deduper: NotificationDeduper | None = None


def get_notification_deduper(ttl_seconds: int) -> NotificationDeduper:
    """获取全局通知去重器单例

    说明：ttl_seconds 只在首次创建时生效；后续调用会复用同一个实例。
    """
    global _deduper
    if _deduper is None:
        _deduper = NotificationDeduper(ttl_seconds=ttl_seconds)
    return _deduper
