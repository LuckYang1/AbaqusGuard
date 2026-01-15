"""
飞书 Webhook 通知客户端（适配飞书集成流程）
"""
import socket
from datetime import datetime
from pathlib import Path

import requests

from src.config.settings import get_settings
from src.models.job import JobInfo


class WebhookClient:
    """飞书 Webhook 通知客户端"""

    def __init__(self):
        """初始化客户端"""
        self.settings = get_settings()
        self.webhook_url = self.settings.FEISHU_WEBHOOK_URL

    def send(self, title: str, content: str, is_success: bool = True) -> bool:
        """
        发送飞书集成流程 Webhook 消息

        Args:
            title: 消息标题
            content: 消息内容
            is_success: 是否成功

        Returns:
            是否发送成功
        """
        if not self.webhook_url:
            if self.settings.VERBOSE:
                print("未配置 Webhook URL,跳过通知")
            return False

        # 状态标识
        status = "成功" if is_success else "失败"
        status_icon = "[完成]" if is_success else "[失败]"

        # 构建飞书集成流程 Webhook 的消息格式
        # message_type 必须为 "text"，其他为自定义键值对
        # 使用粗体和 Emoji 让消息更易读
        title_with_emoji = f"🚀 {title}" if is_success else f"❌ {title}"
        full_message = f"**{title_with_emoji}**\n\n{content}\n\n🖥️ 计算机: {socket.gethostname()}\n⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        payload = {
            "message_type": "text",
            "title": title,
            "content": content,
            "status": status,
            "status_icon": status_icon,
            "is_success": is_success,
            "computer": socket.gethostname(),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            # 完整消息文本，方便在流程中直接使用
            "message": full_message
        }

        if self.settings.VERBOSE:
            print(f"发送 Webhook: {title}")

        try:
            response = requests.post(
                self.webhook_url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=10,
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    if self.settings.VERBOSE:
                        print("Webhook 通知发送成功")
                    return True
                else:
                    print(f"Webhook 返回错误: {result}")
                    return False
            else:
                print(f"Webhook 请求失败: HTTP {response.status_code}")
                return False

        except requests.RequestException as e:
            print(f"Webhook 通知发送失败: {e}")
            return False

    def send_job_start(self, job: JobInfo) -> bool:
        """发送作业开始通知"""
        content = f"""作业名称: {job.name}
工作目录: {job.work_dir}
计算机: {job.computer}
开始时间: {job.start_time.strftime('%Y-%m-%d %H:%M:%S')}

正在计算中，请等待完成通知..."""
        return self.send("[Abaqus] 计算开始", content, is_success=True)

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

    def send_job_progress(self, job: JobInfo) -> bool:
        """发送进度更新通知"""
        duration = job.duration or "计算中"

        # 获取 .sta 文件最后几行
        sta_lines = self._get_sta_last_lines(job, count=3)
        sta_section = f"\n.sta 最后记录:\n{sta_lines}" if sta_lines else ""

        content = f"""作业名称: {job.name}
已运行: {duration}

当前进度:
Step: {job.step} | Increment: {job.increment} | Step Time: {job.step_time:.3f} | Inc Time: {job.inc_time:.4f} | Total Time: {job.total_time:.2f}{sta_section}"""
        return self.send("[Abaqus] 计算进度", content, is_success=True)

    def send_job_complete(self, job: JobInfo) -> bool:
        """发送作业完成通知"""
        is_success = job.status.value == "成功"
        content = f"""作业名称: {job.name}
计算结果: {job.result or job.status.value}
计算耗时: {job.duration or '未知'}
ODB大小: {job.odb_size_mb} MB"""
        return self.send(f"[{job.status.value}] Abaqus 计算完成", content, is_success=is_success)

    def send_job_error(self, job: JobInfo, error: str) -> bool:
        """发送异常通知"""
        content = f"""作业名称: {job.name}
工作目录: {job.work_dir}
错误信息: {error}"""
        return self.send("[异常] Abaqus 计算错误", content, is_success=False)


# 全局客户端实例
_client: WebhookClient = None


def get_webhook_client() -> WebhookClient:
    """获取 Webhook 客户端单例"""
    global _client
    if _client is None:
        _client = WebhookClient()
    return _client
