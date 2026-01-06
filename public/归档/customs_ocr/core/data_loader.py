"""
数据加载模块
从 OCR识别报文.json 中加载图片信息
"""
import json
from typing import List
from .models import ImageInfo


def load_input_data(json_path: str) -> List[ImageInfo]:
    """
    从JSON文件加载图片信息
    
    Args:
        json_path: JSON文件路径
        
    Returns:
        ImageInfo对象列表
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    image_infos = []
    operate_images = data.get('content', {}).get('operateImage', [])
    
    for img_data in operate_images:
        image_info = ImageInfo(
            image_id=str(img_data.get('imageId', '')),
            image_url=img_data.get('imageUrl', ''),
            att_type_code=img_data.get('attTypeCode', 0),
            width=int(img_data.get('imageWidth', 0)) if img_data.get('imageWidth') else None,
            height=int(img_data.get('imageHeight', 0)) if img_data.get('imageHeight') else None
        )
        image_infos.append(image_info)

    return image_infos, operate_images
