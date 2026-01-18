"企业微信 Webhook 通知客户端\n发送企业微信机器人消息，内容与飞书保持一致\n"

import json
import socket
from datetime import datetime
from pathlib import Path

import requests

from src.config.settings import get_settings
from src.core.notify_dedupe import get_notification_deduper
from src.models.job import JobInfo


class WecomWebhookClient:
    """企业微信 Webhook 通知客户端"""

    def __init__(self):
        """初始化客户端"""
        self.settings = get_settings()
        self.webhook_url = self.settings.WECOM_WEBHOOK_URL

    def _send_markdown(self, content: str, webhook_url: str | None = None) -> bool:
        """
        发送企业微信 Markdown 消息

        Args:
            content: Markdown 格式的消息内容

        Returns:
            是否发送成功
        """
        target_url = webhook_url or self.settings.WECOM_WEBHOOK_URL or self.webhook_url
        if not target_url:
            if self.settings.VERBOSE:
                print("未配置企业微信 Webhook URL，跳过通知")
            return False

        payload = {"msgtype": "markdown", "markdown": {"content": content}}

        try:
            response = requests.post(
                target_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=10,
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("errcode") == 0:
                    if self.settings.VERBOSE:
                        print("企业微信通知发送成功")
                    return True
                else:
                    print(f"企业微信返回错误: {result}")
                    return False
            else:
                print(f"企业微信请求失败: HTTP {response.status_code}")
                return False

        except requests.RequestException as e:
            print(f"企业微信通知发送失败: {e}")
            return False

    def send(
        self,
        title: str,
        content: str,
        is_success: bool = True,
        job: JobInfo | None = None,
        idempotency_key: str = "",
        webhook_url: str | None = None,
    ) -> bool:
        """
        发送企业微信通知（Markdown 格式）

        Args:
            title: 消息标题
            content: 消息内容
            is_success: 是否成功
            job: 作业信息（可选）

        Returns:
            是否发送成功
        """
        deduper = get_notification_deduper(self.settings.NOTIFY_DEDUPE_TTL)
        dedupe_key = idempotency_key
        if idempotency_key and webhook_url:
            dedupe_key = f"{idempotency_key}@{webhook_url}"
        if dedupe_key and not deduper.should_send(dedupe_key):
            if self.settings.VERBOSE:
                print(f"跳过重复通知: {title}")
            return False

        # 状态标识
        # 企业微信 Markdown 支持的字体颜色: info(绿色), comment(灰色), warning(橙红色)
        status_color = "info" if is_success else "warning"

        if job:
            status_text = job.status.value
        else:
            status_text = "成功" if is_success else "失败"

        # 构建企业微信 Markdown 消息
        title_with_emoji = f"🚀 {title}" if is_success else f"❌ {title}"

        markdown_content = f"""### {title_with_emoji}
✅ 状态: <font color=\"{status_color}\">{status_text}</font>

{content}

---\n🖥️ 计算机: {socket.gethostname()}
⏰ 时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} """

        if self.settings.VERBOSE:
            print(f"发送企业微信: {title}")

        return self._send_markdown(markdown_content, webhook_url=webhook_url)

    def send_job_start(self, job: JobInfo, webhook_url: str | None = None) -> bool:
        """发送作业开始通知"""
        content = f"""作业名称: {job.name}
工作目录: {job.work_dir}
计算机: {job.computer}
开始时间: {job.start_time.strftime("%Y-%m-%d %H:%M:%S")}

正在计算中，请等待完成通知..."""
        key = f"wecom:job:{job.name}@{job.work_dir}#{int(job.start_time.timestamp())}:start"
        return self.send(
            "[Abaqus] 计算开始",
            content,
            is_success=True,
            job=job,
            idempotency_key=key,
            webhook_url=webhook_url,
        )

    def _get_sta_last_lines(self, job: JobInfo, count: int = 3) -> str:
        """获取 .sta 文件的最后几行"""
        try:
            sta_file = Path(job.work_dir) / f"{job.name}.sta"
            if not sta_file.exists():
                return ""

            with open(sta_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            # 获取最后几行数据行（以数字开头）
            data_lines = []
            for line in reversed(lines):
                line = line.strip()
                if line and line[0].isdigit():
                    data_lines.insert(0, line)
                    if len(data_lines) >= count:
                        break

            return "\n".join(data_lines) if data_lines else ""

        except Exception:
            return ""

    def _format_progress_bar(
        self, current: float, total: float, length: int = 10
    ) -> str:
        """
        生成文本进度条（统一使用飞书的实心样式）

        Args:
            current: 当前进度
            total: 总时间
            length: 进度条长度

        Returns:
            进度条字符串，如 "▓▓▓▓▓▓░░░░ 60.0% (18.5 / 31.0)"
        """
        if total <= 0:
            return ""

        percent = min(current / total, 1.0)
        filled = int(percent * length)
        bar = "▓" * filled + "░" * (length - filled)
        return f"{bar} {percent * 100:.1f}% ({current:.2f} / {total:.2f})"

    def send_job_progress(self, job: JobInfo, webhook_url: str | None = None) -> bool:
        """发送进度更新通知"""
        duration = job.duration or "计算中"

        # 获取 .sta 文件最后几行
        sta_lines = self._get_sta_last_lines(job, count=3)
        sta_section = f"\n.sta 最后记录:\n{sta_lines}" if sta_lines else ""

        # 生成进度条
        progress_bar = self._format_progress_bar(job.total_time, job.total_step_time)
        progress_line = f"\n进度: {progress_bar}" if progress_bar else ""

        content = f"""作业名称: {job.name}
工作目录: {job.work_dir}
已运行: {duration}

当前进度:
Step: {job.step} | Increment: {job.increment} | Step Time: {job.step_time:.3f} | Inc Time: {job.inc_time:.4f} | Total Time: {job.total_time:.2f}{progress_line}{sta_section}"""
        key = f"wecom:job:{job.name}@{job.work_dir}#{int(job.start_time.timestamp())}:progress:{job.step}:{job.increment}"
        return self.send(
            "[Abaqus] 计算进度",
            content,
            is_success=True,
            job=job,
            idempotency_key=key,
            webhook_url=webhook_url,
        )

    def send_job_complete(self, job: JobInfo, webhook_url: str | None = None) -> bool:
        """发送作业完成通知"""
        is_success = job.status.value == "成功"
        content = f"""作业名称: {job.name}
工作目录: {job.work_dir}
计算结果: {job.result or job.status.value}
计算耗时: {job.duration or "未知"}
Total Time: {job.total_time:.2f}
ODB大小: {job.odb_size_mb} MB"""
        key = f"wecom:job:{job.name}@{job.work_dir}#{int(job.start_time.timestamp())}:complete:{job.status.value}"
        return self.send(
            f"[{job.status.value}] Abaqus 计算完成",
            content,
            is_success=is_success,
            job=job,
            idempotency_key=key,
            webhook_url=webhook_url,
        )

    def send_job_error(
        self, job: JobInfo, error: str, webhook_url: str | None = None
    ) -> bool:
        """发送异常通知"""
        content = f"""作业名称: {job.name}
工作目录: {job.work_dir}
错误信息: {error}"""
        key = f"wecom:job:{job.name}@{job.work_dir}#{int(job.start_time.timestamp())}:error"
        return self.send(
            "[异常] Abaqus 计算错误",
            content,
            is_success=False,
            job=job,
            idempotency_key=key,
            webhook_url=webhook_url,
        )

    def send_orphan_job_warning(
        self,
        job: JobInfo,
        job_info: str,
        duration_str: str,
        webhook_url: str | None = None,
    ) -> bool:
        """
        发送孤立作业警告通知

        Args:
            job: 作业信息
            job_info: 文件信息（从 get_job_info 获取）
            duration_str: 运行时长字符串
        """
        content = f"""作业名称: {job.name}
工作目录: {job.work_dir}

检测原因:
Abaqus 求解器进程已停止运行，但 `.lck` 文件仍然存在。
作业可能被手动终止或异常退出。

最后状态: {job.result}

运行时长: {duration_str}
Total Time: {job.total_time:.2f}

文件信息:
{job_info}

提示: 请检查 .msg 和 .dat 文件了解详细信息
如需清理，请手动删除 .lck 文件"""
        key = f"wecom:job:{job.name}@{job.work_dir}#{int(job.start_time.timestamp())}:orphan"
        return self.send(
            "⚠️ Abaqus 作业异常终止",
            content,
            is_success=False,
            job=job,
            idempotency_key=key,
            webhook_url=webhook_url,
        )


# 全局客户端实例
_client: WecomWebhookClient | None = None


def get_wecom_client() -> WecomWebhookClient:
    """获取企业微信客户端单例"""
    global _client
    if _client is None:
        _client = WecomWebhookClient()
    return _client
