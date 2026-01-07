import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel


# ===================== 模型加载 =====================
# 如果你用本地模型，改成你的本地路径即可
# MODEL_PATH = r"D:/Desktop/YiBao/YiBao/public/guidang/model/multilingual-e5-large"
MODEL_PATH = "D:\Desktop\YiBao\YiBao\public\归档\customs_ocr\model-e5"

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModel.from_pretrained(MODEL_PATH)
model.eval()


# ===================== 向量编码函数 =====================
def encode(text: str) -> torch.Tensor:
    """
    将单条文本编码为 L2-normalized embedding
    """
    batch = tokenizer(
        [text],
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

    # average pooling
    emb = last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]

    # L2 normalize
    emb = F.normalize(emb, p=2, dim=1)
    return emb  # shape: (1, hidden_dim)


# ===================== 相似度计算 =====================
def cosine_similarity(text1: str, text2: str) -> float:
    emb1 = encode(text1)
    emb2 = encode(text2)
    sim = F.cosine_similarity(emb1, emb2)
    return sim.item()


# ===================== 测试 =====================
if __name__ == "__main__":
    text_a = "运输方式:公路运输"
    text_b = "运输方式:BY SEA"

    sim = cosine_similarity(text_a, text_b)

    print("Text A:", text_a)
    print("Text B:", text_b)
    print(f"Cosine Similarity: {sim:.4f}")
