"""
.inp 文件解析器
解析 Abaqus 输入文件获取分析步时间信息
"""
from pathlib import Path
from typing import Set


# 无时间参数的分析步类型
NO_TIME_STEP_TYPES = {
    "GEOSTATIC",
    "FREQUENCY",
    "BUCKLE",
    "FREQUENCY",
}


def parse_total_step_time(inp_file: Path) -> float:
    """
    解析 .inp 文件获取所有分析步的时间总和

    Args:
        inp_file: .inp 文件路径

    Returns:
        总分析步时间，解析失败返回 0.0
    """
    if not inp_file.exists():
        return 0.0

    total_time = 0.0
    in_step = False
    step_type_found = False
    current_step_type = ""

    try:
        with open(inp_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_stripped = line.strip()

                # 跳过空行和注释行
                if not line_stripped or line_stripped.startswith("**"):
                    continue

                # 检测分析步开始
                if line_stripped.startswith("*Step,"):
                    in_step = True
                    step_type_found = False
                    current_step_type = ""
                    continue

                if in_step and not step_type_found:
                    # 这行应该是分析类型 (*Static, *Dynamic, *Geostatic, 等)
                    if line_stripped.startswith("*"):
                        # 提取分析类型（去掉星号和空格，转大写）
                        current_step_type = line_stripped[1:].strip().upper().split(",")[0].strip()
                        step_type_found = True

                        # 检查是否是无时间参数的分析步
                        if current_step_type in NO_TIME_STEP_TYPES:
                            # 跳过此类分析步
                            in_step = False
                            step_type_found = False
                    continue

                if in_step and step_type_found:
                    # 这行应该是参数行
                    # 跳过以 * 开头的行（可能是其他关键字）
                    if line_stripped.startswith("*"):
                        in_step = False
                        step_type_found = False
                        continue

                    # 解析参数行，第二个值是时间
                    parts = line_stripped.split(",")
                    if len(parts) >= 2:
                        try:
                            step_time = float(parts[1].strip())
                            total_time += step_time
                        except ValueError:
                            # 解析失败，尝试第一个值（某些格式如 *Dynamic, Explicit）
                            try:
                                step_time = float(parts[0].strip())
                                # 只有当第一个值是有效数字时才累加
                                if parts[0].strip().lstrip("-").replace(".", "").isdigit():
                                    total_time += step_time
                            except ValueError:
                                pass

                    in_step = False
                    step_type_found = False

    except Exception as e:
        print(f"解析 .inp 文件失败 {inp_file}: {e}")
        return 0.0

    return total_time


def test_parse(inp_file: Path) -> dict:
    """
    测试解析功能，返回详细结果

    Args:
        inp_file: .inp 文件路径

    Returns:
        包含解析结果的字典
    """
    if not inp_file.exists():
        return {"error": "文件不存在"}

    steps = []
    total_time = 0.0
    in_step = False
    step_type_found = False
    current_step_type = ""
    current_step_name = ""

    with open(inp_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            if not line_stripped or line_stripped.startswith("**"):
                continue

            if line_stripped.startswith("*Step,"):
                in_step = True
                step_type_found = False
                # 提取步名称
                if "name=" in line_stripped:
                    name_part = line_stripped.split("name=")[1].split(",")[0].strip()
                    current_step_name = name_part
                continue

            if in_step and not step_type_found:
                if line_stripped.startswith("*"):
                    current_step_type = line_stripped[1:].strip().upper().split(",")[0].strip()
                    step_type_found = True

                    if current_step_type in NO_TIME_STEP_TYPES:
                        steps.append({
                            "name": current_step_name,
                            "type": current_step_type,
                            "time": 0.0,
                            "note": "无时间参数"
                        })
                        in_step = False
                        step_type_found = False
                continue

            if in_step and step_type_found:
                if line_stripped.startswith("*"):
                    in_step = False
                    step_type_found = False
                    continue

                parts = line_stripped.split(",")
                step_time = 0.0
                time_found = False

                if len(parts) >= 2:
                    try:
                        step_time = float(parts[1].strip())
                        time_found = True
                    except ValueError:
                        try:
                            step_time = float(parts[0].strip())
                            if parts[0].strip().lstrip("-").replace(".", "").isdigit():
                                time_found = True
                        except ValueError:
                            pass

                steps.append({
                    "name": current_step_name,
                    "type": current_step_type,
                    "time": step_time,
                    "raw": line_stripped
                })

                if time_found:
                    total_time += step_time

                in_step = False
                step_type_found = False

    return {
        "file": str(inp_file),
        "total_time": total_time,
        "steps": steps,
        "step_count": len(steps)
    }
