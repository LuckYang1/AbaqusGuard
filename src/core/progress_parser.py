"""
.sta 文件解析器
解析 Abaqus 状态文件获取作业进度信息
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class StaParser:
    """Abaqus .sta 文件解析器"""

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

    def parse(self) -> Dict[str, any]:
        """
        解析 .sta 文件

        Returns:
            包含进度信息的字典:
            {
                "step": int,           # 当前Step
                "increment": int,      # 当前Increment
                "total_time": float,   # Total Time/Freq
                "step_time": float,    # Step Time/LPF
                "inc_time": float,     # Inc of Step Time/LPF
                "start_time": datetime, # 作业开始时间
                "status": str,         # 作业状态
                "last_line": str,      # 最后一行内容
            }
        """
        result = {
            "step": 0,
            "increment": 0,
            "total_time": 0.0,
            "step_time": 0.0,
            "inc_time": 0.0,
            "start_time": None,
            "status": "unknown",
            "last_line": "",
        }

        if not self.sta_file.exists():
            return result

        try:
            with open(self.sta_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            if not lines:
                return result

            # 解析第一行获取开始时间
            result["start_time"] = self._parse_start_time(lines[0])

            # 解析最后一行状态
            last_line = lines[-1].strip() if lines else ""
            result["last_line"] = last_line
            result["status"] = self._get_status_from_line(last_line)

            # 解析进度数据（倒序查找最后一行数据）
            for line in reversed(lines):
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
            "1": 1, "一": 1,
            "2": 2, "二": 2,
            "3": 3, "三": 3,
            "4": 4, "四": 4,
            "5": 5, "五": 5,
            "6": 6, "六": 6,
            "7": 7, "七": 7,
            "8": 8, "八": 8,
            "9": 9, "九": 9,
            "10": 10, "十": 10,
            "11": 11, "十一": 11,
            "12": 12, "十二": 12,
        }
        return month_map.get(month_str, 1)

    def _is_data_line(self, line: str) -> bool:
        """
        判断是否为数据行
        数据行以数字开头,格式如:   1     1   1     6     0     6  0.100
        """
        line = line.strip()
        if not line:
            return False
        # 跳过标题行
        if any(keyword in line.upper() for keyword in ["STEP", "INC", "SEVERE", "SUMMARY", "ITER"]):
            return False
        # 检查是否以数字开头
        return line[0].isdigit()

    def _parse_data_line(self, line: str) -> Optional[Dict]:
        """
        解析数据行
        格式:   1     1   1     6     0     6  0.100      0.100      0.1000
        列:     STEP  INC ATT SEVERE EQUIL TOTAL  TOTAL      STEP       INC OF
                          DISCON ITERS ITERS  TIME/    TIME/LPF    TIME/LPF
                          ITERS               FREQ
        """
        try:
            # 分割空白字符
            parts = line.split()
            if len(parts) >= 8:
                return {
                    "step": int(parts[0]),
                    "increment": int(parts[1]),
                    "total_time": float(parts[7]),
                    "step_time": float(parts[8]) if len(parts) > 8 else 0.0,
                    "inc_time": float(parts[9]) if len(parts) > 9 else 0.0,
                }
        except (ValueError, IndexError):
            pass

        return None

    def _get_status_from_line(self, line: str) -> str:
        """
        根据最后一行判断状态

        Returns:
            "success", "failed", "running", "unknown"
        """
        line_upper = line.upper()

        if self.STATUS_SUCCESS in line_upper:
            return "success"
        elif self.STATUS_NOT_COMPLETED in line_upper or self.STATUS_ERROR in line_upper:
            return "failed"
        elif line:
            # 有内容但不是已知完成状态,可能是运行中
            return "running"

        return "unknown"

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
