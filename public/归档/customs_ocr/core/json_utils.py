"""
JSON 工具模块
用于解析和验证模型返回的JSON
"""
import json
import re
import re
from typing import Dict, List, Optional


def parse_and_validate(json_str: str) -> Optional[List[Dict]]:
    """
    解析并验证JSON字符串 (期望返回列表格式)
    
    Args:
        json_str: 原始JSON字符串
        
    Returns:
        解析后的列表，失败返回None
    """
    if not json_str:
        return None
    
    # 尝试直接解析
    try:
        data = json.loads(json_str)
        if validate_structure(data):
            return data
    except json.JSONDecodeError:
        pass
    
    # 尝试去除markdown标记
    cleaned = remove_markdown_markers(json_str)
    try:
        data = json.loads(cleaned)
        if validate_structure(data):
            return data
    except json.JSONDecodeError:
        pass
    
    # 尝试提取JSON部分 (支持提取数组 [])
    extracted = extract_json(json_str)
    if extracted:
        try:
            data = json.loads(extracted)
            if validate_structure(data):
                return data
        except json.JSONDecodeError:
            pass
    
    return None


def remove_markdown_markers(text: str) -> str:
    """
    移除markdown标记
    
    Args:
        text: 原始文本
        
    Returns:
        清理后的文本
    """
    # 移除开头的```json或```
    text = re.sub(r'^```json\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^```\s*', '', text)
    
    # 移除结尾的```
    text = re.sub(r'\s*```\s*$', '', text)
    
    return text.strip()


def extract_json(text: str) -> Optional[str]:
    """
    从文本中提取JSON部分 (优先提取数组 [], 然后提对象 {})
    
    Args:
        text: 原始文本
        
    Returns:
        提取的JSON字符串，失败返回None
    """
    # 优先尝试提取数组
    start_array = text.find('[')
    end_array = text.rfind(']')
    
    if start_array != -1 and end_array != -1 and end_array > start_array:
        return text[start_array:end_array+1]

    # 兼容回退：尝试提取对象
    start_obj = text.find('{')
    end_obj = text.rfind('}')
    
    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
        return text[start_obj:end_obj+1]
    
    return None


def validate_structure(data: list) -> bool:
    """
    验证JSON结构是否符合要求 (期望为列表格式)
    
    Args:
        data: 解析后的列表数据
        
    Returns:
        是否符合结构要求
    """
    if not isinstance(data, list):
        return False
    
    for item_data in data:
        if not isinstance(item_data, dict):
            return False
            
        # 检查必需的键
        if 'image_id' not in item_data or 'preDecHead' not in item_data or 'preDecList' not in item_data:
            return False
        
        # 检查preDecHead是否为列表
        if not isinstance(item_data['preDecHead'], list):
            return False
        
        # 检查preDecList是否为列表的列表
        if not isinstance(item_data['preDecList'], list):
            return False
        
        # 验证preDecHead中的每个元素
        for item in item_data['preDecHead']:
            if not validate_field_item(item):
                return False
        
        # 验证preDecList中的每个商品
        for product_fields in item_data['preDecList']:
            if not isinstance(product_fields, list):
                return False
            for item in product_fields:
                if not validate_field_item(item):
                    return False
    
    return True


def validate_field_item(item: Dict) -> bool:
    """
    验证单个字段项是否符合要求
    
    Args:
        item: 字段项字典
        
    Returns:
        是否符合要求
    """
    if not isinstance(item, dict):
        return False
    
    # 检查必需的键
    if 'keyDesc' not in item or 'value' not in item or 'pixel' not in item:
        return False
    
    # 检查pixel是否为包含4个元素的列表
    if not isinstance(item['pixel'], list) or len(item['pixel']) != 4:
        return False
    
    # 检查pixel中的值是否都是数字
    for coord in item['pixel']:
        if not isinstance(coord, (int, float)):
            return False
    
    return True

def parse_mainfactor_json(json_str: str) -> Optional[List[Dict]]:
    """
    解析申报要素的JSON字段 (期望为数组格式)
    """
    # 尝试去除markdown标记
    cleaned = remove_markdown_markers(json_str)
    # print(f"[DEBUG]模型输出部分: {cleaned}")
    extracted = extract_json(json_str)
    
    if extracted:
        try:
            data = json.loads(extracted)
            if isinstance(data, list):
                 return data
            # 如果不小心返回了对象且包含 gmodel 包装，剥离包装返回数组本身
            if isinstance(data, dict) and 'gmodel' in data:
                 return data.get('gmodel', [])
            return data
        except json.JSONDecodeError:
            pass
    
    return None
