"""
JSON 工具模块
用于解析和验证模型返回的JSON
"""
import json
import re
from typing import Dict, Optional


def parse_and_validate(json_str: str) -> Optional[Dict]:
    """
    解析并验证JSON字符串
    
    Args:
        json_str: 原始JSON字符串
        
    Returns:
        解析后的字典，失败返回None
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
    
    # 尝试提取JSON部分
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
    从文本中提取JSON部分
    
    Args:
        text: 原始文本
        
    Returns:
        提取的JSON字符串，失败返回None
    """
    # 尝试找到第一个 { 和最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    
    return None


def validate_structure(data: Dict) -> bool:
    """
    验证JSON结构是否符合要求
    
    Args:
        data: 解析后的字典
        
    Returns:
        是否符合结构要求
    """
    if not isinstance(data, dict):
        return False
    
    # 检查必需的键
    if 'preDecHead' not in data or 'preDecList' not in data:
        return False
    
    # 检查preDecHead是否为列表
    if not isinstance(data['preDecHead'], list):
        return False
    
    # 检查preDecList是否为列表的列表
    if not isinstance(data['preDecList'], list):
        return False
    
    # 验证preDecHead中的每个元素
    for item in data['preDecHead']:
        if not validate_field_item(item):
            return False
    
    # 验证preDecList中的每个商品
    for product_fields in data['preDecList']:
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
