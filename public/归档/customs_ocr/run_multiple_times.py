import os
import random
import subprocess
from pathlib import Path

# ====== 配置区 ======
MAIN_PY = r"d:\Desktop\YiBao\public\归档\customs_ocr\main.py"
INPUT_DIR = Path(r"d:\Desktop\YiBao\public\JSON\OCR识别报文")
OUTPUT_DIR = Path(r"d:\Desktop\YiBao\public\JSON\VLM识别报文")

RANDOM_COUNT = 100   # 随机抽取数量
PYTHON_BIN = "python"  # 或者写绝对路径 /home/wzh/miniconda3/envs/YIBAO/bin/python
# ===================

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 取所有 json 文件
all_files = sorted(INPUT_DIR.glob("*.json"))
if len(all_files) < RANDOM_COUNT:
    raise ValueError(f"文件总数只有 {len(all_files)}，不足 {RANDOM_COUNT}")

# 随机抽样
selected_files = random.sample(all_files, RANDOM_COUNT)

print(f"随机选取 {len(selected_files)} 个文件开始处理")

for idx, input_path in enumerate(selected_files, 1):
    output_path = OUTPUT_DIR / input_path.name

    print(f"[{idx}/{RANDOM_COUNT}] 处理 {input_path.name}")

    subprocess.run(
        [
            PYTHON_BIN,
            MAIN_PY,
            str(input_path),
            str(output_path),
        ],
        check=True
    )

print("随机批量处理完成")