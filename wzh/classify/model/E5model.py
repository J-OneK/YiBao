import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
from torch import Tensor


def average_pool(last_hidden_states: Tensor,
                 attention_mask: Tensor) -> Tensor:
    last_hidden = last_hidden_states.masked_fill(
        ~attention_mask[..., None].bool(), 0.0
    )
    return last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]


# ===== 1. 模型加载 =====
tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
model = AutoModel.from_pretrained("intfloat/multilingual-e5-large")
model.eval()


# ===== 2. 构造类别原型 =====
water = ["passage: 水路运输"]
air = ["passage: 航空运输"]
land = ["passage: 铁路运输"]

query = ["query: by sea"]   # 待分类输入


def encode(texts, normalize=True):
    batch = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=128,
        return_tensors="pt"
    )
    with torch.no_grad():
        outputs = model(**batch)

    embeddings = average_pool(
        outputs.last_hidden_state,
        batch["attention_mask"]
    )

    if normalize:
        embeddings = F.normalize(embeddings, p=2, dim=1)

    return embeddings


# ===== 3. 计算 embedding =====
emb_water = encode(water)      # shape: (1, dim)
emb_air = encode(air)
emb_land = encode(land)
emb_query = encode(query)


# ===== 4. 相似度计算 =====

# 4.1 方式一：余弦相似度（最推荐）
cos_water = F.cosine_similarity(emb_query, emb_water)
cos_air = F.cosine_similarity(emb_query, emb_air)
cos_land = F.cosine_similarity(emb_query, emb_land)

# 4.2 方式二：归一化后矩阵乘（等价于 cosine）
dot_water = emb_query @ emb_water.T
dot_air = emb_query @ emb_air.T
dot_land = emb_query @ emb_land.T

# 4.3 方式三：未归一化点积（一般不推荐，仅作对比）
emb_query_raw = encode(query, normalize=False)
emb_air_raw = encode(air, normalize=False)

raw_dot = emb_query_raw @ emb_air_raw.T


print("=== Cosine similarity ===")
print("water:", cos_water.item())
print("air:", cos_air.item())
print("land:", cos_land.item())

print("\n=== Normalized dot product ===")
print("water:", dot_water.item())
print("air:", dot_air.item())
print("land:", dot_land.item())

print("\n=== Raw dot product (not recommended) ===")
print("query · air:", raw_dot.item())