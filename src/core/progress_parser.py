"""
.sta 文件解析器
解析 Abaqus 状态文件获取作业进度信息
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class StaParser:
    """Abaqus .sta 文件解析器，支持 Standard 和 Explicit 两种格式"""

    # 状态判断关键字
    STATUS_SUCCESS = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY"
    STATUS_NOT_COMPLETED = "THE ANALYSIS HAS NOT BEEN COMPLETED"
    STATUS_ERROR = "THE ANALYSIS HAS BEEN TERMINATED DUE TO AN ERROR"

    def __init__(self, sta_file: Path):
        """
        初始化解析器

        Args:
            sta_file: .sta 文件路径
        """
        self.sta_file = Path(sta_file)
        self.is_explicit = False  # 是否为 Explicit 分析

    def parse(self) -> Dict[str, Any]:
        """
        解析 .sta 文件，自动识别 Standard 和 Explicit 格式

        Returns:
            包含进度信息的字典:
            {
                "step": int,           # 当前Step
                "increment": int,      # 当前Increment
                "total_time": float,   # Total Time/Freq
                "step_time": float,    # Step Time/LPF
                "inc_time": float,     # Inc of Step Time/LPF (Standard) 或 Stable Increment (Explicit)
                "attempts": int,       # 尝试次数
                "start_time": datetime, # 作业开始时间
                "status": str,         # 作业状态
                "last_line": str,      # 最后一行内容
                "raw_lines": List[str], # 最后几行原始数据
                "is_explicit": bool,   # 是否为 Explicit 分析
            }
        """
        result = {
            "step": 0,
            "increment": 0,
            "total_time": 0.0,
            "step_time": 0.0,
            "inc_time": 0.0,
            "attempts": 0,
            "start_time": None,
            "status": "unknown",
            "last_line": "",
            "raw_lines": [],
            "is_explicit": False,
        }

        if not self.sta_file.exists():
            return result

        try:
            with open(self.sta_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            if not lines:
                return result

            # 检测是否为 Explicit 分析（扫描前 10 行查找 "Abaqus/Explicit"）
            header_lines = "".join(lines[:10]).upper()
            self.is_explicit = "ABAQUS/EXPLICIT" in header_lines
            result["is_explicit"] = self.is_explicit

            # 解析第一行获取开始时间（跳过空行）
            first_line = ""
            for line in lines[:10]:
                if line.strip():
                    first_line = line
                    break
            result["start_time"] = self._parse_start_time(first_line)

            # 解析状态：不要只看“最后一行”，因为末尾经常是数据行
            # 采用倒序扫描关键字：优先命中 success/failed，否则再回退为 running/unknown
            last_line = ""
            for line in reversed(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith("INSTANCE"):
                    last_line = stripped
                    break
            result["last_line"] = last_line

            status = self._get_status_from_lines(lines)
            result["status"] = status

            # 获取最后30行非空行（Explicit 文件可能有更多信息行）
            last_lines = [line.rstrip() for line in lines[-30:] if line.strip()]
            result["raw_lines"] = last_lines[-5:]  # 保留最后5行

            # 解析进度数据（倒序查找最后一行数据）
            for line in reversed(last_lines):
                line = line.strip()
                if self._is_data_line(line):
                    data = self._parse_data_line(line)
                    if data:
                        result.update(data)
                        break

        except Exception as e:
            print(f"解析 .sta 文件失败 {self.sta_file}: {e}")

        return result

    def _parse_start_time(self, first_line: str) -> Optional[datetime]:
        """
        从第一行解析开始时间
        格式: Abaqus/Standard 2024   DATE 14-1月-2026 TIME 05:51:43
        """
        try:
            # 匹配 DATE 和 TIME
            date_match = re.search(r"DATE\s+([\d\-]+月\-[\d]+)", first_line)
            time_match = re.search(r"TIME\s+([\d:]+)", first_line)

            if date_match and time_match:
                date_str = date_match.group(1)
                time_str = time_match.group(1)

                # 解析日期格式: 14-1月-2026
                # 使用正则提取日、月、年
                date_parts = re.split(r"[-月]+", date_str)
                if len(date_parts) >= 3:
                    day = int(date_parts[0])
                    month = self._parse_chinese_month(date_parts[1])
                    year = int(date_parts[2])

                    # 解析时间
                    hour, minute, second = map(int, time_str.split(":"))

                    return datetime(year, month, day, hour, minute, second)

        except Exception as e:
            print(f"解析开始时间失败: {e}")

        return None

    @staticmethod
    def _parse_chinese_month(month_str: str) -> int:
        """解析中文月份"""
        month_map = {
            "1": 1,
            "一": 1,
            "2": 2,
            "二": 2,
            "3": 3,
            "三": 3,
            "4": 4,
            "四": 4,
            "5": 5,
            "五": 5,
            "6": 6,
            "六": 6,
            "7": 7,
            "七": 7,
            "8": 8,
            "八": 8,
            "9": 9,
            "九": 9,
            "10": 10,
            "十": 10,
            "11": 11,
            "十一": 11,
            "12": 12,
            "十二": 12,
        }
        return month_map.get(month_str, 1)

    def _is_data_line(self, line: str) -> bool:
        """
        判断是否为数据行

        Standard 格式:   1     1   1     6     0     6  0.100
        Explicit 格式:   2528254  1.415E+00 1.415E+00  02:20:34 2.079E-07 ...
        """
        line = line.strip()
        if not line:
            return False
        # 跳过标题行和状态行
        line_upper = line.upper()
        skip_keywords = [
            "STEP",
            "INC",
            "SEVERE",
            "SUMMARY",
            "ITER",
            "ABAQUS",
            "DATE",
            "TIME",
            "COMPLETED",
            "ANALYSIS",
            "DISCON",
            "FREQ",
            "MONITOR",
            "RIKS",
            "TOTAL",
            "INSTANCE",
            "DOMAIN",
            "OUTPUT",
            "FIELD",
            "FRAME",
            "WARNING",
            "NOTE",
            "ERROR",
            "MEMORY",
            "SCALING",
            "MASS",
            "INERTIA",
            "ELEMENT",
            "NODE",
            "WEIGHT",
            "CRITICAL",
            "STABLE",
            "STATISTICS",
            "MEAN",
            "PREPROCESSOR",
            "SOLUTION",
            "PROGRESS",
            "ORIGIN",
            "INFORMATION",
            "CONTACT",
            "OVERCLOSURE",
            "PENETRAT",
        ]
        if any(keyword in line_upper for keyword in skip_keywords):
            return False
        # 检查是否以数字开头
        return line[0].isdigit()

    def _parse_data_line(self, line: str) -> Optional[Dict]:
        """
        解析数据行，支持 Standard 和 Explicit 两种格式

        Standard 格式:
            STEP  INC ATT SEVERE EQUIL TOTAL  TOTAL      STEP       INC OF
                          DISCON ITERS ITERS  TIME/    TIME/LPF    TIME/LPF
                          ITERS               FREQ
            1     1   1     6     0     6  0.100      0.100      0.1000

        Explicit 格式:
                      STEP     TOTAL      WALL      STABLE    CRITICAL    KINETIC      TOTAL    PERCENT
            INCREMENT     TIME      TIME      TIME   INCREMENT     ELEMENT     ENERGY     ENERGY  CHNG MASS
              2528254  1.415E+00 1.415E+00  02:20:34 2.079E-07       12515  3.953E+04 -8.964E+08  9.900E+03
        """
        try:
            # 分割空白字符
            parts = line.split()

            if self.is_explicit:
                # Explicit 格式解析
                # 列: INCREMENT, STEP_TIME, TOTAL_TIME, WALL_TIME, STABLE_INCREMENT, CRITICAL_ELEMENT, ...
                if len(parts) >= 6:
                    return {
                        "step": 1,  # Explicit 通常只有一个 step
                        "increment": int(parts[0]),  # INCREMENT
                        "step_time": float(parts[1]),  # STEP TIME
                        "total_time": float(parts[2]),  # TOTAL TIME (第3列，用户需要的)
                        "inc_time": float(parts[4]),  # STABLE INCREMENT (稳定时间增量)
                        "attempts": 0,
                    }
            else:
                # Standard 格式解析
                if len(parts) >= 7:
                    return {
                        "step": int(parts[0]),
                        "increment": int(parts[1]),
                        "attempts": int(parts[2]) if len(parts) > 2 else 0,
                        "total_time": float(parts[6]),  # Total Time/Freq (第7列)
                        "step_time": float(parts[7])
                        if len(parts) > 7
                        else 0.0,  # Step Time/LPF (第8列)
                        "inc_time": float(parts[8])
                        if len(parts) > 8
                        else 0.0,  # Inc of Step Time/LPF (第9列)
                    }
        except (ValueError, IndexError):
            pass

        return None

    def _get_status_from_lines(self, lines: List[str]) -> str:
        """从多行内容中推断状态（更稳健）

        说明：.sta 文件末尾经常是数值数据行，直接取最后一行会误判。
        策略：倒序扫描文本行，优先匹配成功/失败关键字；若都未出现，再回退。

        Args:
            lines: .sta 文件所有行

        Returns:
            "success", "failed", "running", "unknown"
        """
        # 倒序扫描，尽快命中结束标识
        for raw in reversed(lines):
            line = raw.strip()
            if not line:
                continue

            line_upper = line.upper()
            if self.STATUS_SUCCESS in line_upper:
                return "success"
            if (
                self.STATUS_NOT_COMPLETED in line_upper
                or self.STATUS_ERROR in line_upper
            ):
                return "failed"

        # 没有出现明确完成/失败关键字：如果文件存在且有内容，通常表示运行中
        return "running" if any(l.strip() for l in lines) else "unknown"

    def _get_status_from_line(self, line: str) -> str:
        """兼容旧接口：从单行推断状态"""
        return self._get_status_from_lines([line])

    @classmethod
    def get_status_from_file(cls, sta_file: Path) -> str:
        """
        从 .sta 文件获取状态

        Args:
            sta_file: .sta 文件路径

        Returns:
            "success", "failed", "running", "unknown"
        """
        parser = cls(sta_file)
        result = parser.parse()
        return result.get("status", "unknown")

    @classmethod
    def extract_start_time(cls, sta_file: Path) -> Optional[datetime]:
        """
        从 .sta 文件提取开始时间

        Args:
            sta_file: .sta 文件路径

        Returns:
            开始时间,失败返回 None
        """
        parser = cls(sta_file)
        result = parser.parse()
        return result.get("start_time")


def get_job_info(sta_path: Path) -> str:
    """
    获取作业详细信息

    Args:
        sta_path: .sta 文件路径

    Returns:
        格式化的作业信息
    """
    info_lines = []

    if sta_path.exists():
        # 文件大小
        size_mb = sta_path.stat().st_size / (1024 * 1024)
        info_lines.append(f"STA文件: {size_mb:.2f} MB")

        # 修改时间
        mtime = datetime.fromtimestamp(sta_path.stat().st_mtime)
        info_lines.append(f"最后修改: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

    # 检查 .odb 文件
    odb_path = sta_path.with_suffix(".odb")
    if odb_path.exists():
        odb_size_mb = odb_path.stat().st_size / (1024 * 1024)
        info_lines.append(f"ODB文件: {odb_size_mb:.2f} MB")

    # 检查 .dat 文件
    dat_path = sta_path.with_suffix(".dat")
    if dat_path.exists():
        dat_size_mb = dat_path.stat().st_size / (1024 * 1024)
        info_lines.append(f"DAT文件: {dat_size_mb:.2f} MB")

    return "\n".join(info_lines) if info_lines else "无额外信息"
