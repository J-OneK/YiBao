def generate_prompt(hs_code, mainfactor_string):
    """
    根据每个商品的具体情况生成 User Prompt
    """
    user_content = f"""
    请处理以下商品：
    **HS编码**：{hs_code}
    **申报要素定义 (Mainfactor)**：{mainfactor_string}
    
    请仔细阅读图片，找到该商品的规格型号栏或备注栏，提取上述 mainfactor 定义的所有要素。
    注意：前两项（品牌类型、出口享惠情况）必须转为数字代码！
    请直接输出结果字符串。
    """
    return user_content

# --- 模拟数据 ---
# 假设这是从你的接口拿到的数据
current_goods = {
    "hs_code": "9406900090",
    "mainfactor": "0:品牌类型;1:出口享惠情况;2:材质;3:内部配置;4:规格（尺寸）;5:GTIN;6:CAS;"
}

# --- 生成 Prompt ---
system_prompt = """你是一个专业的报关单证识别助手。你的任务是从单据图片中提取特定商品的申报要素值。

### 核心指令
用户会提供一个**申报要素定义字符串**（格式如 "0:品牌类型;1:出口享惠情况;..."）。请严格按照定义中**要素项的下标顺序**，从图片中提取对应的值。

### 关键规则（必须遵守）
1. **格式要求**：将提取出的值用 "|" 符号拼接成一个字符串返回，不要包含下标或要素名称。
   - 示例输出：`0|0|木制|家具支撑用|...`
2. **特殊字段转码**：
   - **品牌类型**（通常是第0项）：
     - 看到“无品牌” -> 输出 `0`
     - 看到“境内自主品牌” -> 输出 `1`
     - 看到“境内收购品牌” -> 输出 `2`
     - 看到“境外品牌（贴牌生产）” -> 输出 `3`
     - 看到“境外品牌（其他）” -> 输出 `4`
   - **出口享惠情况**（通常是第1项）：
     - 看到“不享受优惠关税” -> 输出 `0`
     - 看到“享受优惠关税” -> 输出 `1`
     - 看到“不能确定” -> 输出 `2`
     - 看到“不适用于进口报关单” -> 输出 `3`
3. **空值处理**：如果图片中找不到某项要素（如GTIN、CAS），请在该位置填入 `null` 或空字符串，但分隔符 "|" 必须保留以维持位置正确。"""
# (填入上面的 System Prompt 内容)
user_prompt = generate_prompt(
    current_goods["name"], 
    current_goods["hs_code"], 
    current_goods["mainfactor"]
)

# --- 调用大模型 (以 Qwen-VL 为例) ---
# messages = [
#     {"role": "system", "content": system_prompt},
#     {"role": "user", "content": [{"type": "image", "image": "path/to/img.jpg"}, {"type": "text", "text": user_prompt}]}
# ]
# response = model.chat(messages)