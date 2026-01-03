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
    source_list = field['sourceList']
    
    # 生成parsedValue（简化版本：取第一个sourceList的value）
    parsed_value = source_list[0]['value'] if source_list else ''
    
    # 转换坐标
    processed_sources = []
    for source in source_list:
        image_id = source['imageId']
        pixel = source['pixel']
        
        # 获取图片信息
        image_info = image_map.get(image_id)
        if not image_info or not image_info.width or not image_info.height:
            logger.warning(f"未找到图片 {image_id} 的尺寸信息，使用原始坐标")
            processed_sources.append({
                'value': source['value'],
                'startx': int(pixel[0]),
                'starty': int(pixel[1]),
                'endx': int(pixel[2]),
                'endy': int(pixel[3]),
                'imageId': image_id
            })
        else:
            # 转换归一化坐标到实际坐标
            processed_sources.append({
                'value': source['value'],
                'startx': normalize_to_real(pixel[0], image_info.width),
                'starty': normalize_to_real(pixel[1], image_info.height),
                'endx': normalize_to_real(pixel[2], image_info.width),
                'endy': normalize_to_real(pixel[3], image_info.height),
                'imageId': image_id
            })
    
    return {
        'keyDesc': key_desc,
        'key': key,
        'parsedValue': parsed_value,
        'sourceList': processed_sources
    }


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
                'imageId': imageId
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

def transform_final_output(data):
    """
    转换最终输出文件格式为OCR.json
    """
    # 初始化目标结构
    target_json = {
        "head": {
            "resultCode": "0",
            "resultMessage": "识别成功",
            "version": "1.0",
            "timestampStr": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        },
        "content": {
            "preDecHead": [],
            "preDecList": [],
            "preDecContainer": [], # 保持为空或按需处理
            "extend": {} 
        }
    }

    # 1. 转换 preDecHead
    if "preDecHead" in data:
        for item in data["preDecHead"]:
            target_json["content"]["preDecHead"].append(transform_item(item))

    # 2. 转换 preDecList (嵌套列表)
    if "preDecList" in data:
        for row in data["preDecList"]:
            new_row = []
            for item in row:
                new_row.append(transform_item(item))
            target_json["content"]["preDecList"].append(new_row)

    return target_json