from pathlib import Path
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel

# === 模型只加载一次 ===
_tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
_model = AutoModel.from_pretrained("intfloat/multilingual-e5-large")
_model.eval()

# === embeddings 目录：基于当前文件 ===
BASE_DIR = Path(__file__).resolve().parent



def verify_pt_and_choose_top(key_desc: str, input_text: str) -> str:
    """
    验证 key_desc.pt 是否可正常使用
    输入 input_text
    输出相似度最高的 paramKey
    """

    

    store = torch.load('监管方式.pt')

    if not store:
        raise ValueError("pt 文件为空")

    # ---- 计算 input embedding ----
    batch = _tokenizer(
        [input_text],
        padding=True,
        truncation=True,
        max_length=128,
        return_tensors="pt"
    )

    with torch.no_grad():
        outputs = _model(**batch)

    attention_mask = batch["attention_mask"]
    last_hidden = outputs.last_hidden_state.masked_fill(
        ~attention_mask[..., None].bool(), 0.0
    )
    input_emb = last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]
    input_emb = F.normalize(input_emb, p=2, dim=1)

    # ---- 取出 pt 中 embedding ----
    param_values = []
    embeddings = []

    for k, v in store.items():
        if "embedding" not in v or "paramKey" not in v:
            raise ValueError(f"pt 结构不合法，缺字段: {k}")

        param_values.append(k)
        embeddings.append(v["embedding"])

    embeddings = torch.stack(embeddings)

    # ---- 相似度计算 ----
    sims = F.cosine_similarity(input_emb, embeddings)
    best_idx = sims.argmax().item()

    best_param_value = param_values[best_idx]
    best_param_key = store[best_param_value]["paramKey"]
    best_score = sims[best_idx].item()

    print(
        f"[VERIFY] key_desc={key_desc} | input='{input_text}'\n"
        f"         best_match='{best_param_value}' | paramKey={best_param_key} | score={best_score:.4f}"
    )

    return best_param_key

verify_pt_and_choose_top("监管方式", "海关处理")