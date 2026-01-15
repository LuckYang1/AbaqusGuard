"""
进程检测模块
通过检测 Abaqus 求解器进程判断作业状态
使用 Windows tasklist 命令，不依赖 psutil
"""
import subprocess
from typing import Optional

from src.config.settings import get_settings


class ProcessDetector:
    """Abaqus 进程检测器"""

    # Abaqus 求解器进程名列表
    ABAQUS_PROCESSES = [
        "standard.exe",     # Abaqus/Standard
        "explicit.exe",     # Abaqus/Explicit
        "ABQSMAStd.exe",    # Abaqus/Standard (Abaqus for SIMPACK)
        "ABQSMAExp.exe",    # Abaqus/Explicit (Abaqus for SIMPACK)
    ]

    def __init__(self):
        """初始化检测器"""
        self.settings = get_settings()
        self._cached_result: Optional[bool] = None
        self._cache_time: Optional[float] = None
        self._cache_ttl = 5.0  # 缓存5秒

    def _run_tasklist(self) -> str:
        """
        运行 tasklist 命令获取进程列表

        Returns:
            进程列表输出文本（小写）
        """
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode == 0:
                return result.stdout.lower()
            return ""
        except Exception:
            return ""

    def is_abaqus_running(self) -> bool:
        """
        检测是否有 Abaqus 求解器进程正在运行

        Returns:
            是否有 Abaqus 进程运行
        """
        output = self._run_tasklist()

        if not output:
            # 无法确定时，假设进程在运行，避免误报
            return True

        # 检查是否有任何 Abaqus 进程
        for process_name in self.ABAQUS_PROCESSES:
            if process_name.lower() in output:
                return True

        return False

    def is_job_process_running(self, job_name: str) -> bool:
        """
        检测指定作业的 Abaqus 进程是否在运行

        Args:
            job_name: 作业名称

        Returns:
            该作业的进程是否在运行
        """
        # 简化实现：如果有 Abaqus 进程运行，则认为作业可能正在运行
        # 更精确的检测需要检查命令行参数，但 tasklist 输出格式不够友好
        return self.is_abaqus_running()

    def get_abaqus_processes(self) -> list:
        """
        获取所有 Abaqus 相关进程

        Returns:
            进程信息列表
        """
        abaqus_procs = []
        output = self._run_tasklist()

        if not output:
            return abaqus_procs

        # 解析 CSV 格式输出
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue

            # CSV 格式: "进程名","PID","会话名","会话#","内存使用"
            parts = line.split(',')
            if len(parts) >= 2:
                proc_name = parts[0].strip('"').lower()
                pid = parts[1].strip('"')

                # 检查是否为 Abaqus 进程
                if any(p.lower() in proc_name for p in self.ABAQUS_PROCESSES):
                    abaqus_procs.append({
                        'pid': pid,
                        'name': proc_name,
                    })

        return abaqus_procs


# 全局检测实例
_detector = None


def get_process_detector() -> ProcessDetector:
    """获取进程检测器单例"""
    global _detector
    if _detector is None:
        _detector = ProcessDetector()
    return _detector
