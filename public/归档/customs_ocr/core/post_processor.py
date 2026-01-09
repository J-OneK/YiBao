"""
后处理模块
对聚合后的数据进行最终处理，包括：
1. 生成parsedValue
2. 坐标转换
注意：字段key已在聚合阶段补充
"""
import logging
from typing import Dict, List
from .models import ImageInfo
from .mainfactor_utils import normalize_values
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel
from typing import Dict
import os
import json
import time
from config.field_mapping import ATT_TYPE_NAMES_EN

logger = logging.getLogger(__name__)


def process_final_output(aggregated_data: Dict, image_infos: List[ImageInfo]) -> Dict:
    """
    处理最终输出
    
    Args:
        aggregated_data: 聚合后的数据（已包含key）
        image_infos: 图片信息列表（用于获取原图尺寸）
        
    Returns:
        最终格式化的数据
    """
    # 创建image_id到ImageInfo的映射
    image_map = {info.image_id: info for info in image_infos}
    
    # 处理表头
    processed_head = []
    for field in aggregated_data['preDecHead']:
        processed_field = process_field(field, image_map)
        processed_head.append(processed_field)
    
    # 处理表体
    processed_list = []
    for product_fields in aggregated_data['preDecList']:
        processed_product = []
        for field in product_fields:
            processed_field = process_field(field, image_map)
            processed_product.append(processed_field)
        processed_list.append(processed_product)
    
    return {
        "preDecHead": processed_head,
        "preDecList": processed_list
    }


def process_field(field: Dict, image_map: Dict[str, ImageInfo]) -> Dict:
    """
    处理单个字段
    
    Args:
        field: 字段数据（已包含key）
        image_map: 图片信息映射
        
    Returns:
        处理后的字段
    """
    key_desc = field['keyDesc']
    key = field['key']
    if_unify = field['if_unify']
    source_list = field['sourceList']
    
    # 生成parsedValue（简化版本：取第一个sourceList的value）
    parsed_value = source_list[0]['value'] if source_list else ''
    
    # 生成transformedValue
    transformedValue_total = choose_top_similarity(key_desc, parsed_value)

    # 转换坐标
    processed_sources = []
    for source in source_list:
        image_id = source['imageId']
        pixel = source['pixel']
        att_type_code = source['att_type_code']
        # 获取图片信息
        image_info = image_map.get(image_id)
        if if_unify:
            if not image_info or not image_info.width or not image_info.height:
                logger.warning(f"未找到图片 {image_id} 的尺寸信息，使用原始坐标")
                processed_sources.append({
                    'value': source['value'],
                    'transformedValue': transformedValue_total,
                    'startx': int(pixel[0]),
                    'starty': int(pixel[1]),
                    'endx': int(pixel[2]),
                    'endy': int(pixel[3]),
                    'imageId': image_id,
                    'attTypeCode': att_type_code
                })
            else:
                # 转换归一化坐标到实际坐标
                processed_sources.append({
                    'value': source['value'],
                    'transformedValue': transformedValue_total,
                    'startx': normalize_to_real(pixel[0], image_info.width),
                    'starty': normalize_to_real(pixel[1], image_info.height),
                    'endx': normalize_to_real(pixel[2], image_info.width),
                    'endy': normalize_to_real(pixel[3], image_info.height),
                    'imageId': image_id,
                    'attTypeCode': att_type_code
                })
        else:
            if not image_info or not image_info.width or not image_info.height:
                logger.warning(f"未找到图片 {image_id} 的尺寸信息，使用原始坐标")
                processed_sources.append({
                    'value': source['value'],
                    'transformedValue': source['value'],
                    'startx': int(pixel[0]),
                    'starty': int(pixel[1]),
                    'endx': int(pixel[2]),
                    'endy': int(pixel[3]),
                    'imageId': image_id,
                    'attTypeCode': att_type_code
                })
            else:
                # 转换归一化坐标到实际坐标
                processed_sources.append({
                    'value': source['value'],
                    'transformedValue': source['value'],
                    'startx': normalize_to_real(pixel[0], image_info.width),
                    'starty': normalize_to_real(pixel[1], image_info.height),
                    'endx': normalize_to_real(pixel[2], image_info.width),
                    'endy': normalize_to_real(pixel[3], image_info.height),
                    'imageId': image_id,
                    'attTypeCode': att_type_code
                })
    
    return {
        'keyDesc': key_desc,
        'key': key,
        'parsedValue': parsed_value,
        'transformedValue': transformedValue_total, 
        'if_unify': if_unify,
        'sourceList': processed_sources
    }

KEY_DESC_ALIAS_MAP = {

        "运抵国": "国家",
        "贸易国": "国家",
        "原产国": "国家",
        "最终目的国": "国家",

        "指运港": "港口",
        
        "运输方式": "运输方式",
        
        "监管方式": "监管方式",
        
        "征免性质": "征免方式",

        "离境口岸": "口岸",
        
        "包装种类": "包装种类",

        "运费币制": "币制",
        "保费币制": "币制",
        "成交币制": "币制",
        "杂费币制": "币制",
        "币制": "币制",

        "成交方式": "成交方式",

        "境内货源地": "境内货源地",

        "征减免税方式": "征减免税方式",
        
        "成交计量单位": "计量单位",

    }

def choose_top_similarity(key_desc: str, parsed_value: str) -> str:
    """
    1. 先在 key_desc.json 中做精确匹配（paramValue / spt）
    2. 若无命中，再使用 key_desc.pt 做 embedding 相似度匹配
    """
    convert_class = KEY_DESC_ALIAS_MAP.get(key_desc, None)
    if convert_class is None:
        return parsed_value
    
    
    # ===================== 1. 精确匹配（JSON） =====================
    json_path = f"./presaved_embeddings/{convert_class}.json"
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        result_list = data.get("message", {}).get("resultList", [])
        for item in result_list:
            param_key = item.get("paramKey", "").strip()
            if not param_key:
                continue
            
            if parsed_value == param_key:
                print(f'{key_desc} 字段：精确匹配 {parsed_value} -> {param_key}')
                return param_key

            # paramValue
            if parsed_value == item.get("paramValue", "").strip():
                print(f'{key_desc} 字段：精确匹配 {parsed_value} -> {param_key}')
                return param_key

            # spt1 / spt2 / spt3
            for spt_field in ("spt1", "spt2", "spt3"):
                if parsed_value == item.get(spt_field, "").strip():
                    print(f'{key_desc} 字段：精确匹配 {spt_field} -> {param_key}')
                    return param_key

    # ===================== 2. embedding 相似度（PT） =====================
    MODEL_PATH = './model-e5'

    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModel.from_pretrained(MODEL_PATH)
    model.eval()

    def encode_text(text: str):
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
        embeddings = last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]
        embeddings = F.normalize(embeddings, p=2, dim=1)
        return embeddings  # (1, dim)

    input_emb = encode_text(parsed_value)

    pt_path = f"./presaved_embeddings/{convert_class}.pt"
    store: Dict[str, Dict] = torch.load(pt_path)

    param_values = list(store.keys())
    embeddings = torch.stack([store[v]["embedding"] for v in param_values])

    similarity = F.cosine_similarity(input_emb, embeddings)
    idx = similarity.argmax().item()

    matched_param_value = param_values[idx]
    matched_param_key = store[matched_param_value]["paramKey"]
    matched_score = similarity[idx].item()
    
    print(
        f'{key_desc} 字段：embedding 匹配'f' {parsed_value} -> {matched_param_value} -> {matched_param_key} (sim={matched_score:.4f})' 
    )

    return matched_param_key


def normalize_to_real(normalized_coord: float, actual_size: int) -> int:
    """
    将归一化坐标[0-999]转换为实际坐标
    
    Args:
        normalized_coord: 归一化坐标
        actual_size: 实际尺寸
        
    Returns:
        实际坐标
    """
    return int(normalized_coord * actual_size / 999)

def process_mainfactors(results: List[Dict]) -> List[Dict]:
    """
    处理申报要素识别结果，提取有效的mainfactor数据
    去除掉无效内容后选取内容最丰富（即最长）的结果
    Args:
        results: 识别结果列表
        
    Returns:
        有效的mainfactor数据列表
    """
    best_results = {}

    # 预定义无效集合
    ignore_set = {'null', '0', ''}

    for entry in results:
        for model in entry.get('gmodel', []):
            code = model.get('codeTs')
            # 归一化商品编码
            code = normalize_values([code])[0]
            mf = model.get('mainfactors')
            pixel = model.get('pixel')
            imageId = model.get('imageId')
            attTypeCode = model.get('attTypeCode')
            if not code or not mf:
                continue

            current_score = 0
            for part in mf.split('|'):
                p = part.strip()
                if p and p not in ignore_set:
                    current_score += len(p)
            clean_item = {
                'codeTs': code, 
                'mainfactors': mf,
                'pixel': pixel,
                'imageId': imageId,
                'attTypeCode': attTypeCode
            }
            if code not in best_results or current_score > best_results[code][0]:
                best_results[code] = (current_score, clean_item)
    
    return [item[1] for item in best_results.values()]

def transform_source_list(source_list):
    """
    转换 sourceList 中的每一项。
    1. 计算 width 和 height。
    2. 映射坐标字段 (startx/starty -> axisX/axisY)。
    3. 类型转换 (imageId str -> int)。
    4. 添加 processBitMap (默认为 "0")。
    5. 【过滤】彻底移除 extractFrom 等不相关字段。
    """
    transformed = []
    for src in source_list:
        # 计算宽高
        start_x = src.get('startx', 0)
        start_y = src.get('starty', 0)
        end_x = src.get('endx', 0)
        end_y = src.get('endy', 0)
        
        width = end_x - start_x
        height = end_y - start_y
        
        # 转换 imageId 类型
        img_id = src.get('imageId')
        if img_id is not None:
            try:
                img_id = int(img_id)
            except ValueError:
                pass # 如果转换失败保持原样

        new_src = {
            "attType": ATT_TYPE_NAMES_EN.get(src.get('attTypeCode'), "未知文档"),
            "imageId": img_id,
            "transformValue": src.get('transformedValue'),
            "originalValue": src.get('value'),
            "normalizedValue": src.get('value'),
            # sourceList 子项也可能有 processBitMap，默认给 "0"
            "processBitMap": src.get('processBitMap', "0"),
            "axisX": start_x,
            "sepValue": src.get('value'),
            "axisY": start_y,
            "width": width,
            "attTypeCode": src.get('attTypeCode'),
            "height": height
        }
        
        # 注意：此处不再包含 extractFrom
        transformed.append(new_src)
    return transformed

def transform_item(item):
    """
    转换单个字段对象 (preDecHead 或 preDecList 中的项)。
    """
    # 优先使用 transformedValue 作为最终 value 和 normalizedValue
    final_value = item.get('transformedValue', item.get('parsedValue', ''))
    
    new_item = {
        "processBitMap": "0", 
        "sourceList": transform_source_list(item.get('sourceList', [])),
        "source_image": transform_source_list(item.get('sourceList', []))[0].get('imageId'),
        "originalValue": item.get('parsedValue'), # 保留原始 parsedValue
        "normalizedValue": final_value,
        "keyDesc": item.get('keyDesc'),
        "value": final_value,
        "key": item.get('key'),
    }
    # print(transform_source_list(item.get('sourceList', []))[0])
    # 注意：此处不再包含 extractFrom 和 parsedValue (根级别)
    
    return new_item

def transform_operate_image(operate_list):
    """
    转换 operateImage 列表。
    根据图片指示，剔除不需要的 Key。
    """
    keys_to_remove = {
        "callOcrOpen", 
        "extractSource", 
        "preAttTypeCode", 
        "parseCode", 
        "inputDocType", 
        "classifySource"
    }

    transformed = []
    for item in operate_list:
        new_item = {}
        for k, v in item.items():
            if k not in keys_to_remove:
                new_item[k] = v
        transformed.append(new_item)
    return transformed


def transform_final_output(data, operate_images, head_list):
    """
    转换最终输出文件格式为OCR.json
    """
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    head_list["timestampStr"] = current_time
    # 初始化目标结构
    target_json = {
        "head": head_list,
        "content": {
            "preDecHead": [],
            "preDecList": [],
            "operateImage": [],
            "preDecContainer": [] # 保持为空或按需处理
            
        }
    }

    # 1. 转换 preDecHead
    if "preDecHead" in data:
        for item in data["preDecHead"]:
            transformed_item = transform_item(item)
            #  检查是否是柜号 (key 为 containerNo)
            if item.get("key") == "containerNo":
                # 放入 preDecContainer，格式为 [[item]]
                target_json["content"]["preDecContainer"].append([transformed_item])
            else:
                # 放入 preDecHead
                target_json["content"]["preDecHead"].append(transformed_item)

    # 2. 转换 preDecList (嵌套列表)
    if "preDecList" in data:
        for row in data["preDecList"]:
            new_row = []
            for item in row:
                new_row.append(transform_item(item))
            target_json["content"]["preDecList"].append(new_row)
    
    # 3. 转换 operateImage
    transformed_item = transform_operate_image(operate_images)
    for item in transformed_item:
        target_json["content"]["operateImage"].append(item)

    return target_json