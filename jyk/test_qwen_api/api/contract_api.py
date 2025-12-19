from openai import OpenAI
import os

def test_qwen3_vl_flash_without_thinking():
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
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "http://smartebao-production-ocr.oss-cn-shanghai.aliyuncs.com/02502/8d81c47c9c0b4dd7b436e4695830a506/3_RELNBI09149%E6%8A%A5%E5%85%B3.pdf.png"
                        },
                    },
                    {"type": "text", "text": """
### 报关文档识别要求
请识别文档中的 **表头（preDecHead）** 和 **表体（preDecList）** ，严格按照指定 JSON 格式输出（无对应字段不输出）：

#### 一、表头（preDecHead）识别规则
1. 核心字段池：['保费币制', '保费标记', '保费率', '境内收发货人名称', '境内收发货人海关代码', '境内收发货人社会信用代码', '境外收发货人', '备案号', '总价总和', '成交方式', '指运港', '生产销售单位名称', '生产销售单位海关代码', '生产销售单位社会信用代码', '贸易国', '运抵国', '运费币制', '运费标记', '运费率']
2. 同义转换：文档中表述不同但含义一致的字段（如“TO”→“运抵国”），统一将 `keyDesc` 设为字段池中的标准名称
3. 仅输出文档中实际存在的字段，不存在的字段不纳入

#### 二、表体（preDecList）识别规则
1. 核心字段池：['件数单项', '净重单项', '单价', '原产国', '商品名称', '商品编号', '境内货源地', '币制', '总价', '成交单位', '成交数量', '最终目的国', '毛重单项', '法定第一数量', '法定第二数量', '规格型号']
2. 同义转换：同表头规则，非标准表述统一映射为字段池中的标准 `keyDesc`
3. 多商品处理：每个商品单独作为一个子列表，仅输出该商品实际存在的字段

#### 三、输出 JSON 格式要求
- `keyDesc`：必须是上述字段池中的标准名称
- `value`：识别到的具体内容
- `pixel`：字段对应内容的四个坐标点（按实际识别结果填写）
- 严格遵循以下结构，不新增/删除层级或字段：

```json
{
  "preDecHead": [
    {
      "keyDesc": "xx",
      "value": "yy",
      "pixel": "[a,b,c,d]"
    }
  ],
  "preDecList": [
    [
      {
        "keyDesc": "xx",
        "value": "yy",
        "pixel": "[a,b,c,d]"
      }
    ]
  ]
}
"""},
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
    test_qwen3_vl_flash_without_thinking()