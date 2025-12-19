"""
Prompt 模板管理模块
根据文件类型生成不同的 prompt
"""
from config.field_mapping import get_fields_for_type, ATT_TYPE_NAMES


def generate_prompt(att_type_code: int) -> str:
    """
    根据文件类型代码生成 prompt
    
    Args:
        att_type_code: 文件类型代码
        
    Returns:
        完整的 prompt 字符串
    """
    head_fields, list_fields = get_fields_for_type(att_type_code)
    att_type_name = ATT_TYPE_NAMES.get(att_type_code, "未知文档")
    
    # 构建prompt
    prompt = f"""你是一个专业的报关文档识别助手。请仔细分析这张{att_type_name}图片，按照以下要求提取字段信息：

【重要说明】
1. 输出必须严格遵循JSON格式，不要添加任何markdown标记（如```json）
2. 字段名称（keyDesc）必须从提供的标准名称池中选择，不能自己创造
3. 图片中未识别到的字段不应出现在JSON中
4. 对于表头字段，同一keyDesc只能出现一次
5. 对于表体字段，如果有多个商品，每个商品的字段单独记录在一个数组中
6. pixel必须是归一化坐标，范围[0-999]，格式为[左上x, 左上y, 右下x, 右下y]
7. 图片中的字段名称可能与标准名称不完全一致（如"TO USA"对应"运抵国"），需要你判断对应关系

【表头字段标准名称池】（preDecHead）
"""
    
    if head_fields:
        for i, field in enumerate(head_fields, 1):
            prompt += f"{i}. {field}\n"
    else:
        prompt += "无\n"
    
    prompt += "\n【表体字段标准名称池】（preDecList）\n"
    
    if list_fields:
        for i, field in enumerate(list_fields, 1):
            prompt += f"{i}. {field}\n"
    else:
        prompt += "无\n"
    
    prompt += """
【输出格式】
请输出以下JSON格式（不要添加markdown标记）：
```json
{
  "preDecHead": [
    {
      "keyDesc": "字段标准名称",
      "value": "识别到的值",
      "pixel": [左上x, 左上y, 右下x, 右下y]
    }
  ],
  "preDecList": [
    [
      {
        "keyDesc": "字段标准名称",
        "value": "识别到的值",
        "pixel": [左上x, 左上y, 右下x, 右下y]
      }
    ]
  ]
}
```

请开始识别！
"""
    
    return prompt
