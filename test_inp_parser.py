"""测试 inp_parser 解析功能"""
import sys
sys.path.insert(0, r"C:\Users\YSY\Desktop\FS-ABAQUS")

from pathlib import Path
from src.core.inp_parser import parse_total_step_time, test_parse

# 测试文件列表
test_files = [
    "inp_ex/Test-60-RGB.inp",
    "inp_ex/Job-1.inp",
    "inp_ex/Job-2.inp",
    "inp_ex/Job-3.inp",
]

base_path = Path(r"C:\Users\YSY\Desktop\FS-ABAQUS")

print("=" * 60)
print("测试 .inp 文件解析")
print("=" * 60)

for file_name in test_files:
    file_path = base_path / file_name
    print(f"\n文件: {file_name}")

    # 快速解析
    total = parse_total_step_time(file_path)
    print(f"  总时间: {total}")

    # 详细解析
    if file_path.exists():
        result = test_parse(file_path)
        print(f"  分析步数量: {result['step_count']}")
        for step in result['steps']:
            print(f"    - {step['name']}: {step['type']}, 时间={step['time']}")
            if 'note' in step:
                print(f"      ({step['note']})")
