import base64
import mimetypes
import os
import sys

try:
    from openai import OpenAI
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: openai. Install with `pip install openai`."
    ) from exc


DEFAULT_PROMPT = """你是一个专业的单证/表单OCR识别助手。请仔细分析图片内容，按以下要求提取字段信息：
1) 输出必须严格遵循JSON格式，不要添加任何markdown标记。
2) 未识别到的字段不要出现在JSON中。
3) pixel为归一化坐标，范围[0-999]，格式为[左上x, 左上y, 右下x, 右下y]。
4) 仅输出JSON，不要输出解释或额外文字。
5) predechead用于表头字段识别，predeclist用于表体字段识别。
6) 对于表体字段，做到一个商品的字段记录在一个数组中，第一个商品的字段在第一个数组，第二个商品的字段在第二个数组，以此类推。
7) 商品可能出现在多张图片中，按照图片顺序依次识别，例如第一张图片中有两个商品，则第二张图片的第一个商品是整体的第三个商品。
输出格式示例：
{
  "preDecHead": [
    {
      "keyDesc": "字段标准名称",
      "value": "识别到的值",
      "pixel": [0, 0, 0, 0]
    }
  ],
  "preDecList": [
    [
      {
        "keyDesc": "字段标准名称",
        "value": "识别到的值",
        "pixel": [0, 0, 0, 0]
      }
    ]
  ]
}
请开始识别！"""


def _encode_image(path: str) -> str:
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        mime_type = "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def main() -> int:
    # Hardcoded paths for a simple, readable test script.
    image1_path = r"d:\Desktop\YiBao\wzh\multiple pictures at a time\Sheet1_part_1.png"
    image2_path = r"d:\Desktop\YiBao\wzh\multiple pictures at a time\Sheet1_part_2.png"
    output_path = r"d:\Desktop\YiBao\wzh\multiple pictures at a time\reply.txt"

    # Optional: replace DEFAULT_PROMPT with a custom prompt string.
    prompt_text = DEFAULT_PROMPT

    # Model + API config.
    API_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MODEL_NAME = "qwen3-vl-flash"
    api_key = os.getenv("API_KEY")

    if not api_key:
        print("Missing API key. Set OPENAI_API_KEY or pass --api-key.", file=sys.stderr)
        return 2

    img1 = _encode_image(image1_path)
    img2 = _encode_image(image2_path)

    client_kwargs = {"api_key": api_key}
    if API_BASE_URL:
        client_kwargs["base_url"] = API_BASE_URL
    client = OpenAI(**client_kwargs)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": img1}},
                    {"type": "image_url", "image_url": {"url": img2}},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ],
    )

    reply_text = response.choices[0].message.content or ""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(reply_text)

    print(f"Saved response to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
