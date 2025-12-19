from openai import OpenAI
import os
from mainfactor_api import get_mainfactor

system_prompt = """你是一个专业的报关单证识别助手。你的任务是从单据图片中提取特定商品的申报要素值。

### 核心指令
用户会提供一个**申报要素定义字符串**（格式如 "0:品牌类型;1:出口享惠情况;..."）。请严格按照定义中**要素项的下标顺序**，从图片中提取对应的值。

### 关键规则（必须遵守）
1. **格式要求**：将提取出的值用 "|" 符号拼接成一个字符串返回，不要包含下标或要素名称。
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
3. **空值处理**：如果图片中找不到某项要素（如GTIN、CAS），请在该位置填入 `null` 或空字符串，但分隔符 "|" 必须保留以维持位置正确。
### 提取规则
1. 商品信息及其顺序以报关单据中的商品顺序为准，即“商品项号”、“商品编号”、“商品名称”应从报关单据区域的商品信息中提取。
2. 当提供的资料中没有明确标注“商品项号”时，应将“商品项号”的值设定为实际的商品顺序号，从1开始计数。
3. 如果商品规格型号信息不在报关单内，而是存在于另一份资料中，请执行以下操作：
   - 使用“商品编码”和“商品名称”作为关键字。
   - 在规格型号资料中查找与之匹配的记录。
   - 提取对应的规格型号信息。
4. 当某一属性值出现在商品信息的公共区域（如上方或下方）时，该属性值应被视为适用于所有商品，如“品牌类型”、“出口享惠情况”等。
5. 如果“品牌”的属性值后面有“牌”或“无中文名称”等描述时，则将“牌”或“无中文名称”与属性值一起完整地输出，比如出现“SHON牌”，则输出“SHON牌”，比如出现“SHON，无中文名称”，则输出“SHON，无中文名称”。只有当图片中属性值后确实有此关键字时才可以一起输出。
6. 如果“型号”的属性值后面有“等”字时，则将“等”字与属性值一起完整地输出，比如出现“DS-2DE5225W-AE T5等”，则“型号”的属性值应输出“DS-2DE5225W-AE T5等”。只有当图片中属性值后确实有此关键字时才可以一起输出。
### 关键词与属性值对应规则
1. **出口享惠情况**：
   - 关键词：“享惠”、“享受优惠关税”、“不享惠”、“不能确定”
   - 说明：只有当图片中确实存在上述关键词之一时，才将其归类为“出口享惠情况”的属性值。

2. **品牌类型**：
   - 关键词：“境外品牌(贴牌生产)”、“贴牌”、“境外品牌”、“贴牌生产”、“境外品牌(其它)”、“境外品牌(其他)”、“境外其他”、“境外其它”、“境内自主品牌”、“自主品牌”、“境内收购品牌”、“境内收购”、“无品牌类型”
   - 说明：只有当图片中确实存在上述关键词之一时，才将其归类为“品牌类型”的属性值。

3. **用途**：
   - 关键词：“坐”、“坐具”、“座具”、“收纳”、“家具”
   - 说明：只有当图片中确实存在上述关键词之一时，才将其归类为“用途”的属性值。
### 输出要求
1. 必须严格按照任务要求输出，禁止产生其他内容。
2. 必须严格按照图片的原始内容进行结果输出，禁止进行任何原图内容的改动。
3. 所有属性值不准遗漏。
4. 仅输出每个商品编码对应的属性值，禁止输出分析过程。
5. 如果没有识别到上述任何关键词，则不输出任何内容。
6. 严格按照任务中要求的商品数量按实际顺序输出对应的商品规格型号信息。
7. 按照JSON格式输出，不包含任何解释、说明或额外文字。
### 输出示例
```json
[
  {0|0|玻璃，铝合金|花洒|90x90x210CM|null|null},
  {0|0|木制|家具支撑用|...}
   //如果有多组数据，继续添加更多对象
]
```
"""

def test_qwen3_vl_flash_without_thinking(mainfactor):
    user_content = f"""
    申报要素定义：{mainfactor}
    请严格按上述定义的顺序提取值。如果是品牌类型或享惠情况，请转为代码数字。
    若在图片中未识别到相关内容，则不输出任何内容。
    """
    # 初始化OpenAI客户端
    client = OpenAI(
        api_key = os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

    reasoning_content = ""  # 定义完整思考过程
    answer_content = ""     # 定义完整回复
    is_answering = False   # 判断是否结束思考过程并开始回复
    enable_thinking = False
    # 创建聊天完成请求
    completion = client.chat.completions.create(
        model="qwen3-vl-flash",
        messages=[
            {'role': 'system', 'content': system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "http://smartebao-production-ocr.oss-cn-shanghai.aliyuncs.com/dub/002/1/2020/12/23/e2b69000-a81e-4c9b-b262-a51df4700b75/LSK251042615/file/0_19DA70AE6FE5C255DD9168D653EAC78E2079.xls.png"
                        },
                    },
                    {"type": "text", "text": user_content},
                ]
            },
        ],
        stream=True,
        # enable_thinking 参数开启思考过程，thinking_budget 参数设置最大推理过程 Token 数
        extra_body={
            'enable_thinking': False,
            "thinking_budget": 81920},

        # 解除以下注释会在最后一个chunk返回Token使用量
        # stream_options={
        #     "include_usage": True
        # }
        # response_format={"type": "json_object"}
    )

    if enable_thinking:
        print("\n" + "=" * 20 + "思考过程" + "=" * 20 + "\n")

    for chunk in completion:
        # 如果chunk.choices为空，则打印usage
        if not chunk.choices:
            print("\nUsage:")
            print(chunk.usage)
        else:
            delta = chunk.choices[0].delta
            # 打印思考过程
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content != None:
                print(delta.reasoning_content, end='', flush=True)
                reasoning_content += delta.reasoning_content
            else:
                # 开始回复
                if delta.content != "" and is_answering is False:
                    print("\n" + "=" * 20 + "完整回复" + "=" * 20 + "\n")
                    is_answering = True
                # 打印回复过程
                print(delta.content, end='', flush=True)
                answer_content += delta.content

    # print("=" * 20 + "完整思考过程" + "=" * 20 + "\n")
    # print(reasoning_content)
    # print("=" * 20 + "完整回复" + "=" * 20 + "\n")
    # print(answer_content)

if __name__ == "__main__":
    os.environ["DASHSCOPE_API_KEY"] = "sk-3c0fcdd9febc4aca8dc5ff05aead0524" 
    test_qwen3_vl_flash_without_thinking(get_mainfactor("9406900090"))