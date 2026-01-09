from pathlib import Path
import sys

# === 添加 main.py 所在目录到 sys.path ===
sys.path.append(str(Path("/home/wzh/project/YiBao/public/归档/customs_ocr").expanduser()))
from main import main  # 导入 main.py 的 main 函数

# === OCR输入目录和VLM输出目录 ===
input_dir = Path("/home/wzh/project/YiBao/public/JSON/OCR识别报文").expanduser()
output_dir = Path("/home/wzh/project/YiBao/public/JSON/VLM识别报文").expanduser()
output_dir.mkdir(parents=True, exist_ok=True)

# === 明文写索引范围（从1开始计数，更直观） ===
start_idx = 1  # 起始文件序号
end_idx = 2    # 结束文件序号（包含此文件）

# === 按文件名排序，保证顺序一致 ===
all_files = sorted(input_dir.glob("*.json"))

# === 截取指定范围 ===
selected_files = all_files[start_idx-1:end_idx]

if not selected_files:
    print(f"没有找到文件，请检查索引范围: {start_idx}-{end_idx}")
    sys.exit(1)

# === 批量处理 ===
for input_file in selected_files:
    output_file = output_dir / input_file.name  # 输出同名文件
    print(f"处理: {input_file} -> {output_file}")
    main(str(input_file), str(output_file))
