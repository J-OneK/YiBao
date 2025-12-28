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
    #transformedValue_total = choose_top_similarity(key_desc, parsed_value)
    transformedValue_total = parsed_value

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


'''
def choose_top_similarity(key_desc: str, parsed_value: str):
    """
    选择相似度最高的值作为transformedValue
    """
    
    need_transform = {'归属地', '征免性质', '监管方式', '贸易方式', '币制', '成交方式'}
    if key_desc not in need_transform:
        return parsed_value
    else:
        query_text = f"query: {parsed_value}"
        query_emb = encode_fn([query_text])
        best_label = None
        best_score = -1e9

        # 遍历该 key 下的所有子类
        for paramValue, param_emb, paramKey in tensor_store[key_desc].items():
            if param_emb is None:
                continue

            # label_emb shape: (dim,)
            score = torch.matmul(query_emb, param_emb.unsqueeze(1)).item()

            if score > best_score:
                best_score = score
                best_paramKey = paramKey
        return best_paramKey
    

def encode_fn(texts: List[str]):
    tokenizer = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")
    model = AutoModel.from_pretrained("intfloat/multilingual-e5-large")
    model.eval()
    batch = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=256,
        return_tensors="pt"
    )

    with torch.no_grad():
        outputs = model(**batch)

    # E5 推荐：取 CLS 向量
    embeddings = outputs.last_hidden_state[:, 0]

    # L2 normalize，便于 cosine / dot-product
    embeddings = F.normalize(embeddings, p=2, dim=1)

    return embeddings

'''

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