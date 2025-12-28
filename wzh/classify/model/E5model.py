import json
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
from typing import Dict

# ===================== 模型加载 =====================
tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
model = AutoModel.from_pretrained("intfloat/multilingual-e5-large")
model.eval()

# ===================== 辅助函数 =====================
def encode_texts(texts):
    """批量生成文本向量"""
    batch = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=128,
        return_tensors="pt"
    )
    with torch.no_grad():
        outputs = model(**batch)
    # average pooling
    attention_mask = batch["attention_mask"]
    last_hidden = outputs.last_hidden_state.masked_fill(~attention_mask[..., None].bool(), 0.0)
    embeddings = last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]
    embeddings = F.normalize(embeddings, p=2, dim=1)  # L2归一化
    return embeddings

# ===================== 数据加载 =====================
with open("1_运输方式_1009.json", "r", encoding="utf-8") as f:
    data = json.load(f)

result_list = data["message"]["resultList"]

# ===================== 提取 paramKey 和 paramValue =====================
param_dict: Dict[str, str] = {}  # key: paramValue, value: paramKey
values_to_encode = []

for item in result_list:
    value = item.get("paramValue", "").strip()
    key = item.get("paramKey", "").strip()
    if value and key:
        param_dict[value] = key
        values_to_encode.append(value)

# ===================== 生成向量 =====================
embeddings = encode_texts(values_to_encode)

# ===================== 保存向量 =====================
# 保存为字典: paramValue -> (paramKey, embedding tensor)
embedding_store = {}
for i, value in enumerate(values_to_encode):
    embedding_store[value] = {
        "paramKey": param_dict[value],
        "embedding": embeddings[i].cpu()  # 可保存 tensor，也可以转 numpy
    }

# 保存为 torch 文件
torch.save(embedding_store, "param_embeddings.pt")
print(f"保存 {len(embedding_store)} 条 paramValue embedding 到 param_embeddings.pt")