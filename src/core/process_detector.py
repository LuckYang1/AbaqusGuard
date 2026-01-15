"""
进程检测模块
通过检测 Abaqus 求解器进程判断作业状态
"""
import psutil

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

    def is_abaqus_running(self) -> bool:
        """
        检测是否有 Abaqus 求解器进程正在运行

        Returns:
            是否有 Abaqus 进程运行
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                proc_name = proc.info['name'].lower()
                cmdline = proc.info['cmdline']
                if cmdline is None:
                    continue

                # 检查进程名
                if any(proc_name == p.lower() for p in self.ABAQUS_PROCESSES):
                    return True

                # 检查命令行参数
                cmdline_str = ' '.join(cmdline).lower()
                if 'abaqus' in cmdline_str and ('standard' in cmdline_str or 'explicit' in cmdline_str or 'job=' in cmdline_str):
                    return True

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return False

    def get_abaqus_processes(self) -> list:
        """
        获取所有 Abaqus 相关进程

        Returns:
            进程信息列表
        """
        abaqus_procs = []

        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline is None:
                    continue

                cmdline_str = ' '.join(cmdline).lower()

                # 检查是否为 Abaqus 进程
                if 'abaqus' not in cmdline_str:
                    continue

                abaqus_procs.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'cmdline': ' '.join(cmdline),
                    'create_time': proc.info['create_time'],
                })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return abaqus_procs

    def is_job_process_running(self, job_name: str) -> bool:
        """
        检测指定作业的 Abaqus 进程是否在运行

        Args:
            job_name: 作业名称

        Returns:
            该作业的进程是否在运行
        """
        job_name_lower = job_name.lower()

        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                proc_name = proc.info['name'].lower()
                cmdline = proc.info['cmdline']
                if cmdline is None:
                    continue

                cmdline_str = ' '.join(cmdline).lower()

                # 检查是否为 Abaqus 求解器进程
                if not any(p.lower() in proc_name or p.lower() in cmdline_str for p in self.ABAQUS_PROCESSES):
                    continue

                # 检查命令行中是否包含作业名
                # 支持多种格式: -job xxx, job=xxx, 或直接作为参数
                if f'-job{job_name_lower}' in cmdline_str.replace(' ', ''):
                    return True
                if f'-job {job_name_lower}' in cmdline_str:
                    return True
                if f'job={job_name_lower}' in cmdline_str:
                    return True
                # 检查命令行参数中是否直接包含作业名
                for arg in cmdline:
                    if arg.lower() == job_name_lower or arg.lower() == f'job={job_name_lower}':
                        return True

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return False


# 全局检测实例
_detector = None


def get_process_detector() -> ProcessDetector:
    """获取进程检测器单例"""
    global _detector
    if _detector is None:
        _detector = ProcessDetector()
    return _detector
