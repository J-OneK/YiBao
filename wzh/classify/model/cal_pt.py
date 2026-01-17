import json
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
from typing import Dict, List
import os

# ===================== 模型加载 =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "../../../public/归档/customs_ocr/model-e5")

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)
model = AutoModel.from_pretrained(MODEL_PATH, local_files_only=True)
model.eval()


# ===================== 辅助函数 =====================
def encode_texts(texts: List[str]) -> torch.Tensor:
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

    attention_mask = batch["attention_mask"]
    last_hidden = outputs.last_hidden_state.masked_fill(
        ~attention_mask[..., None].bool(), 0.0
    )
    embeddings = last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]
    embeddings = F.normalize(embeddings, p=2, dim=1)
    return embeddings


# ===================== 数据加载 =====================
with open("12_征减免税方式_1010.json", "r", encoding="utf-8") as f:
    data = json.load(f)

result_list = data["message"]["resultList"]


# ===================== 收集所有需要编码的文本 =====================
texts: List[str] = []
meta: List[Dict] = []  # 与 texts 一一对应，记录 paramKey

for item in result_list:
    param_key = item.get("paramKey", "").strip()
    if not param_key:
        continue

    # 1️⃣ paramValue
    param_value = item.get("paramValue", "").strip()
    if param_value:
        texts.append(param_value)
        meta.append({"paramKey": param_key})

    # 2️⃣ spt1 / spt2 / spt3
    for spt_field in ("spt1", "spt2", "spt3"):
        spt_val = item.get(spt_field, "").strip()
        if spt_val:
            texts.append(spt_val)
            meta.append({"paramKey": param_key})


# ===================== 生成向量 =====================
embeddings = encode_texts(texts)


# ===================== 保存向量 =====================
embedding_store: Dict[str, Dict] = {}

for i, text in enumerate(texts):
    embedding_store[text] = {
        "paramKey": meta[i]["paramKey"],
        "embedding": embeddings[i].cpu()
    }

torch.save(embedding_store, "param_embeddings.pt")

print(f"保存 {len(embedding_store)} 条 embedding 到 param_embeddings.pt")
