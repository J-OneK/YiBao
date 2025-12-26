import json
import os
import re
from pathlib import Path

# ================= 配置区域 =================
# 你的JSON文件所在的文件夹路径
RAW_DIR = Path('/Users/1k/code/YiBao/jyk/基础参数类型') 

# 输出的Python文件名
OUTPUT_FILE = 'const_values.py'
# ===========================================

def clean_variable_name(filename):
    """
    将文件名转换为合法的 Python 变量名。
    1. 去掉 .json 后缀
    2. 如果以数字开头，加个前缀 'L_' (List之意)，防止语法错误
    3. 虽然 Python3 支持中文变量名，但为了安全建议大写
    """
    stem = filename.stem
    # 替换掉非法的字符（如空格、横杠）为下划线
    safe_name = re.sub(r'[^\w\u4e00-\u9fa5]', '_', stem)
    
    # 如果开头是数字，加前缀
    if safe_name[0].isdigit():
        safe_name = f"L_{safe_name}"
        
    return safe_name.upper()

def generate_python_lists():
    file_content = [
        "# This file is auto-generated. DO NOT EDIT MANUALLY.",
        "# 包含从JSON中提取的 paramValue 列表",
        "",
        "class ValueLists:",
    ]

    # 检查文件夹是否存在
    if not RAW_DIR.exists():
        print(f"错误：文件夹 {RAW_DIR} 不存在，请检查路径。")
        return

    json_files = list(RAW_DIR.glob('*.json'))
    print(f"找到 {len(json_files)} 个JSON文件，开始处理...")

    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取 resultList
            result_list = data.get('message', {}).get('resultList', [])
            
            # 核心逻辑：只提取 paramValue，并去除空格
            # 增加了防御性判断：必须有 'paramValue' 这个键
            value_list = [
                item['paramValue'].strip() 
                for item in result_list 
                if isinstance(item, dict) and 'paramValue' in item
            ]
            
            # 生成变量名
            var_name = clean_variable_name(file_path)
            
            # 格式化列表为字符串 (ensure_ascii=False 保证中文显示正常)
            list_str = json.dumps(value_list, ensure_ascii=False, indent=4)
            
            # 写入类变量
            file_content.append(f"    # Source: {file_path.name}")
            file_content.append(f"    {var_name} = {list_str}")
            file_content.append("") # 空行分隔
            
            print(f"✔ 已提取: {file_path.name} -> {var_name} ({len(value_list)} 条数据)")

        except Exception as e:
            print(f"❌ 处理失败 {file_path.name}: {e}")

    # 保存文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f_out:
        f_out.write("\n".join(file_content))
        
    print(f"\n处理完成！文件已生成至: {OUTPUT_FILE}")

if __name__ == '__main__':
    generate_python_lists()