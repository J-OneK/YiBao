import json
from collections import OrderedDict
from typing import List, Dict, Any
import os
import json


def merge_predec(json_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    json_list: 多个已加载的 json dict
    return: 合并后的目标 json
    """

    # ========= 合并 preDecHead =========
    head_map = OrderedDict()

    for doc in json_list:
        source = doc.get("source", {})
        att_type = source.get("attType")
        image_id = source.get("imageId")

        for item in doc.get("preDecHead", []):
            key = item["keyDesc"]

            if key not in head_map:
                head_map[key] = {
                    "keyDesc": key,
                    "sepValueList": [],
                    "markColor": "",
                    "finalValue": ""
                }

            head_map[key]["sepValueList"].append({
                "attType": att_type,
                "imageId": image_id,
                "value": item.get("value"),
                "pixel": item.get("pixel")
            })

    merged_predec_head = list(head_map.values())

    # ========= 合并 preDecList =========a
    max_rows = max(len(doc.get("preDecList", [])) for doc in json_list)

    merged_predec_list = []

    for row_idx in range(max_rows):
        row_map = OrderedDict()

        for doc in json_list:
            source = doc.get("source", {})
            att_type = source.get("attType")
            image_id = source.get("imageId")

            predec_list = doc.get("preDecList", [])

            if row_idx >= len(predec_list): # 如果不同文件商品数量不统一，则只合并大家都有的前几个商品
                continue

            for item in predec_list[row_idx]:
                key = item["keyDesc"]

                if key not in row_map:
                    row_map[key] = {
                        "keyDesc": key,
                        "sepValueList": [],
                        "markColor": "",
                        "finalValue": ""
                    }

                row_map[key]["sepValueList"].append({
                    "attType": att_type,
                    "imageId": image_id,
                    "value": item.get("value"),
                    "pixel": item.get("pixel")
                })

        merged_predec_list.append(list(row_map.values()))

    return {
        "preDecHead": merged_predec_head,
        "preDecList": merged_predec_list
    }


if __name__ == "__main__":

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    print(BASE_DIR)
    invoice_path = os.path.join(BASE_DIR, "invoice.json")
    packinglist_path = os.path.join(BASE_DIR, "packing_list.json")

    print("trying:", invoice_path)
    print("exists:", os.path.exists(invoice_path))

    with open(invoice_path, "r", encoding="utf-8") as f:
        invoice = json.load(f)

    with open(packinglist_path, "r", encoding="utf-8") as f:
        packing = json.load(f)

    merged = merge_predec([invoice, packing])

    with open("./wzh/merged.json", "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
