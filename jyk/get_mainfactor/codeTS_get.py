import json
import re

def get_codets_values(json_file):
    values = []
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 遍历 preDecList 中的每一行商品
        # preDecList 是一个二维列表: [ [商品1字段...], [商品2字段...] ]
        for row in data.get("preDecList", []):
            for field in row:
                # 找到 key 为 codeTs 的字段
                if field.get("key") == "codeTs":
                    # 提取 parsedValue
                    val = field.get("parsedValue")
                    if val:
                        values.append(val)
                    break # 找到当前行的 codeTs 后跳出内层循环，进入下一行
                    
    except Exception as e:
        print(f"读取出错: {e}")
        
    return values

def normalize_values(values):
    """
    1. 分割: 处理 "1;4202920000" 这种带分号的情况。
    2. 清洗: 去除小数点等非数字符号。
    3. 过滤: 丢弃长度小于 4 的纯数字 (视为序号)。
    4. 补全: 不足 10 位后补 0。
    """
    valid_values = []
    for v in values:
        parts = re.split(r'[;,\/\|\n]+', str(v))  # 支持多种分隔符
        for part in parts:
            part = part.strip()
            if not part:
                continue

            clean_digits = re.sub(r'[^\d]', '', part) # 去除非数字字符
            if len(clean_digits) < 4: #过滤长度小于4
                continue
            if len(clean_digits) > 10:
                clean_digits = clean_digits[:10] # 截断到10位
            elif len(clean_digits) < 10:
                clean_digits = clean_digits.ljust(10, '0') # 补全到10位
            
            valid_values.append(clean_digits)

    seen = set()
    unique_values = [x for x in valid_values if not (x in seen or seen.add(x))]
    return unique_values



# --- 运行提取 ---
if __name__ == "__main__":
    # 请确保 output.json 在同一目录下，或修改为绝对路径
    result = normalize_values(get_codets_values('output.json'))
    # 打印结果列表
    print(result)
    
    # 或者逐行打印
    # for v in result:
    #     print(v)