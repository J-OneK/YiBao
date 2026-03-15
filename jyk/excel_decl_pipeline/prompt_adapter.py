"""Prompt builder for chunk-level Qwen3-VL extraction."""

from __future__ import annotations

from .field_mapping_loader import get_att_type_name, get_fields_for_type


def generate_prompt(att_type_code: int) -> str:
    head_fields, list_fields = get_fields_for_type(att_type_code)
    att_type_name = get_att_type_name(att_type_code)

    prompt = f"""你是专业的报关单证识别助手。请分析这张{att_type_name}图片块，抽取字段并返回严格 JSON。

【要求】
1. 只输出 JSON，不要 markdown 代码块。
2. keyDesc 只能从下面标准字段池中选择。
3. 未识别字段不要输出。
4. preDecHead 同一 keyDesc 只出现一次。
5. preDecList 按商品逐行组织，每个商品是一组字段。
6. pixel 必须是归一化坐标 [x1, y1, x2, y2]，范围 0-999。
7. 字段名可能和标准字段不完全一致，但输出必须使用标准字段名。
8. 不要编造内容，必须忠实于图片中的文字。

【表头字段池 preDecHead】
"""
    if head_fields:
        for idx, field in enumerate(head_fields, start=1):
            prompt += f"{idx}. {field}\n"
    else:
        prompt += "无\n"

    prompt += "\n【表体字段池 preDecList】\n"
    if list_fields:
        for idx, field in enumerate(list_fields, start=1):
            prompt += f"{idx}. {field}\n"
    else:
        prompt += "无\n"

    prompt += """
【输出格式】
{
  "preDecHead": [
    {
      "keyDesc": "字段标准名称",
      "value": "识别值",
      "pixel": [x1, y1, x2, y2]
    }
  ],
  "preDecList": [
    [
      {
        "keyDesc": "字段标准名称",
        "value": "识别值",
        "pixel": [x1, y1, x2, y2]
      }
    ]
  ]
}
"""
    return prompt

