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

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_MODEL_PATH = os.path.join(_BASE_DIR, "../model-e5")

_TOKENIZER = None
_MODEL = None
_EMBEDDINGS_CACHE: Dict[str, Dict[str, object]] = {}


def _get_text_model():
    global _TOKENIZER, _MODEL
    if _TOKENIZER is None or _MODEL is None:
        _TOKENIZER = AutoTokenizer.from_pretrained(_MODEL_PATH, local_files_only=True)
        _MODEL = AutoModel.from_pretrained(_MODEL_PATH, local_files_only=True)
        _MODEL.eval()
    return _TOKENIZER, _MODEL


def _get_embeddings(convert_class: str):
    cached = _EMBEDDINGS_CACHE.get(convert_class)
    if cached is not None:
        return cached

    pt_path = os.path.join(_BASE_DIR, "../presaved_embeddings", f"{convert_class}.pt")
    if not os.path.exists(pt_path):
        return None

    store: Dict[str, Dict] = torch.load(pt_path)
    param_values = list(store.keys())
    embeddings = torch.stack([store[v]["embedding"] for v in param_values])
    cached = {
        "store": store,
        "param_values": param_values,
        "embeddings": embeddings,
    }
    _EMBEDDINGS_CACHE[convert_class] = cached
    return cached


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
    处理单个字段 (集成角度旋转修正)
    """
    key_desc = field['keyDesc']
    key = field['key']
    if_unify = field['if_unify']
    source_list = field['sourceList']
    
    # 生成parsedValue
    parsed_value = source_list[0]['value'] if source_list else ''
    
    # 生成transformedValue
    transformedValue_total = choose_top_similarity(key_desc, parsed_value)

    # 转换坐标
    processed_sources = []
    for source in source_list:
        image_id = source['imageId']
        pixel = source['pixel']
        if pixel is None:
            logger.warning(f"字段 {key_desc} 的 pixel 为空，填写0，0，0，0作为默认坐标")
            pixel = [0, 0, 0, 0]
            source['pixel'] = [0, 0, 0, 0]  # 同时修改 source 中的 pixel
        att_type_code = source['att_type_code']
        # 获取图片信息
        image_info = image_map.get(image_id)
        
        # 提取图片基础信息
        img_w = image_info.width if image_info else 0
        img_h = image_info.height if image_info else 0

        # 定义一个内部闭包或变量来存储计算出的最终坐标
        final_sx, final_sy, final_ex, final_ey = 0, 0, 0, 0
        
        # 判断是否能获取到有效尺寸
        has_size = image_info and img_w and img_h

        if not has_size:
            logger.warning(f"未找到图片 {image_id} 的尺寸信息，使用原始坐标")
            # 这里的 int转换 保持原样
            final_sx, final_sy, final_ex, final_ey = int(pixel[0]), int(pixel[1]), int(pixel[2]), int(pixel[3])
        else:
            # 1. 先进行归一化转实际坐标
            final_sx = normalize_to_real(pixel[0], img_w)
            final_sy = normalize_to_real(pixel[1], img_h)
            final_ex = normalize_to_real(pixel[2], img_w)
            final_ey = normalize_to_real(pixel[3], img_h)

        # 构造结果字典
        # 根据 if_unify 区分 transformedValue 的取值
        result_item = {
            'value': source['value'],
            'transformedValue': transformedValue_total if if_unify else source['value'],
            'startx': final_sx,
            'starty': final_sy,
            'endx': final_ex,
            'endy': final_ey,
            'imageId': image_id,
            'attTypeCode': att_type_code
        }
        processed_sources.append(result_item)
    
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

        "运费标记": "费用标记",
        "保费标记": "费用标记",
        "杂费标记": "费用标记",

    }

# 缓存字典，用于存储已计算过的字段相似度匹配结果
# key: (key_desc, parsed_value)，value: 匹配结果
_similarity_cache: Dict[tuple, str] = {}

def choose_top_similarity(key_desc: str, parsed_value: str) -> str:
    """
    1. 先在 key_desc.json 中做精确匹配（paramValue / spt）
    2. 若无命中，再使用 key_desc.pt 做 embedding 相似度匹配
    3. 使用缓存机制，避免重复计算相同字段的相似度
    """
    # 如果值为空，直接返回，不进行映射
    if not parsed_value or parsed_value.strip() == "":
        return parsed_value
    
    convert_class = KEY_DESC_ALIAS_MAP.get(key_desc, None)
    if convert_class is None:
        return parsed_value
    
    # 检查缓存，如果已计算过则直接返回
    cache_key = (key_desc, parsed_value)
    if cache_key in _similarity_cache:
        cached_result = _similarity_cache[cache_key]
        print(f'{key_desc} 字段：从缓存获取匹配结果 {parsed_value} -> {cached_result}')
        return cached_result
    
    
    # ===================== 1. 精确匹配（JSON） =====================
    json_path = os.path.join(_BASE_DIR, "../presaved_embeddings", f"{convert_class}.json")
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
                _similarity_cache[cache_key] = param_key
                return param_key

            # paramValue
            if parsed_value == item.get("paramValue", "").strip():
                print(f'{key_desc} 字段：精确匹配 {parsed_value} -> {param_key}')
                _similarity_cache[cache_key] = param_key
                return param_key

            # spt1 / spt2 / spt3
            for spt_field in ("spt1", "spt2", "spt3"):
                spt_value = item.get(spt_field, "").strip()
                if parsed_value == spt_value:
                    print(f'{key_desc} 字段：精确匹配 {parsed_value} -> {param_key}')
                    _similarity_cache[cache_key] = param_key
                    return param_key

    # ===================== 2. embedding 相似度（PT） =====================
    embed_cache = _get_embeddings(convert_class)
    if embed_cache is None:
        _similarity_cache[cache_key] = parsed_value
        return parsed_value

    tokenizer, model = _get_text_model()

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

    param_values = embed_cache["param_values"]
    embeddings = embed_cache["embeddings"]
    store = embed_cache["store"]

    similarity = F.cosine_similarity(input_emb, embeddings)
    idx = similarity.argmax().item()

    matched_param_value = param_values[idx]
    matched_param_key = store[matched_param_value]["paramKey"]
    matched_score = similarity[idx].item()

    if matched_score < 0.85:
        print(f'{key_desc} 字段：embedding 匹配分数过低 {parsed_value} -> {matched_param_value} (sim={matched_score:.4f})，输出空白')
        _similarity_cache[cache_key] = ""
        return ""
    
    print(
        f'{key_desc} 字段：embedding 匹配'f' {parsed_value} -> {matched_param_value} -> {matched_param_key} (sim={matched_score:.4f})' 
    )
    
    _similarity_cache[cache_key] = matched_param_key
    return matched_param_key

def clear_similarity_cache():
    """
    清空相似度匹配缓存
    通常在处理完一个批次后调用，或在需要重新计算所有字段时调用
    """
    global _similarity_cache
    _similarity_cache.clear()
    print(f"相似度匹配缓存已清空")


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
            if not code:
                continue
            if not normalize_values([code]):
                continue
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
            # 使用 | 分割字符串
            parts = mf.split('|')
            # 过滤掉 'null' 字段并替换为空字符串
            cleaned_parts = ['' if part == 'null' else part for part in parts]
            # 用 | 连接回字符串
            mf = '|'.join(cleaned_parts)
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

def normalize_operate_images(operate_images, image_infos=None, angle_threshold=3):
    """
    归一化 operateImage 列表中的角度和尺寸信息
    
    Args:
        operate_images: 图片信息列表
        image_infos: ImageInfo 对象列表，包含预处理后的图片尺寸和OSS URL
        angle_threshold: 角度归一化的阈值（度），已弃用，保留参数兼容性
    
    处理逻辑：
    1. 角度归一化：将所有角度统一设为0（图片已在预处理阶段完成旋转矫正）
    2. 尺寸替换：用 image_infos 中的 width 和 height 替换 imageWidth 和 imageHeight
    3. URL替换：用 image_infos 中的 image_url 替换 imageUrl（如果已上传到OSS）
    """
    # 创建 imageId -> ImageInfo 的映射
    image_info_map = {}
    if image_infos:
        for info in image_infos:
            image_info_map[str(info.image_id)] = info
    
    for img in operate_images:
        # 角度归一化：统一设为0（图片已在预处理时旋转矫正）
        if "angle" in img:
            img["angle"] = 0
        if "imageSuffix" in img:
            img["imageSuffix"] = "png"
        # 用预处理后的尺寸和URL替换
        image_id = str(img.get("imageId", ""))
        if image_id in image_info_map:
            info = image_info_map[image_id]
            
            # 更新宽度和高度
            if info.width is not None and info.width > 0:
                img["imageWidth"] = str(info.width)
                img["originalImageWidth"] = str(info.width)
            if info.height is not None and info.height > 0:
                img["imageHeight"] = str(info.height)
                img["originalImageHeight"] = str(info.height)
            
            # 更新URL为OSS URL（如果存在且不是base64）
            if info.image_url and not info.image_url.startswith('data:'):
                img["imageUrl"] = info.image_url
    
    return operate_images


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


def transform_final_output(data, operate_images, head_list, image_infos=None):
    """
    转换最终输出文件格式为OCR.json
    
    Args:
        data: 处理后的识别数据
        operate_images: 原始 operateImage 列表
        head_list: 头部信息
        image_infos: ImageInfo 对象列表，包含预处理后的图片尺寸
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
    # 3.1 先归一化角度和尺寸（使用预处理后的图片尺寸）
    normalized_images = normalize_operate_images(operate_images, image_infos=image_infos, angle_threshold=3)
    # 3.2 再转换格式
    transformed_item = transform_operate_image(normalized_images)
    for item in transformed_item:
        target_json["content"]["operateImage"].append(item)

    return target_json
