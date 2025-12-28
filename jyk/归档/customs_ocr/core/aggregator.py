"""
聚合模块
将多个图片的识别结果聚合
注意：字段映射和来源验证已在OCR识别阶段完成
支持异步并发处理值一致性判断
"""
import logging
import json
import asyncio
from typing import List, Dict, Tuple, Set
from collections import defaultdict
from openai import AsyncOpenAI
from config import settings
from config.field_mapping import fuzzy_match_key_desc
from .models import ExtractionResult, ExtractedField

logger = logging.getLogger(__name__)


def aggregate_results(results: List[ExtractionResult]) -> Dict:
    """
    聚合多张图片的识别结果
    
    Args:
        results: 识别结果列表
        
    Returns:
        聚合后的字典
    """
    # 聚合表头
    aggregated_head = aggregate_head_fields(results)
    
    # 聚合表体
    aggregated_list = aggregate_list_fields(results)
    
    return {
        "preDecHead": aggregated_head,
        "preDecList": aggregated_list
    }


def aggregate_head_fields(results: List[ExtractionResult]) -> List[Dict]:
    """
    聚合表头字段
    按keyDesc分组，将不同来源的值合并到sourceList
    注意：传入的results中的字段已经过滤和映射，都是有效字段
    
    Args:
        results: 识别结果列表
        
    Returns:
        聚合后的表头列表
    """
    # 按keyDesc分组
    grouped = defaultdict(list)
    
    for result in results:
        for field in result.pre_dec_head:
            grouped[field.key_desc].append({
                'value': field.value,
                'pixel': field.pixel,
                'imageId': field.image_id
            })
    
    # 转换为列表格式，同时补充key
    aggregated = []
    for key_desc, sources in grouped.items():
        # 获取key（在OCR阶段已验证过，这里应能找到）
        key = fuzzy_match_key_desc(key_desc)
        aggregated.append({
            'keyDesc': key_desc,
            'key': key,
            'sourceList': sources
        })
    
    return aggregated


def aggregate_list_fields(results: List[ExtractionResult]) -> List[List[Dict]]:
    """
    聚合表体字段
    按商品顺序聚合，如果不同图片的商品数量不一样，后面的商品聚合来源会更少
    
    Args:
        results: 识别结果列表
        
    Returns:
        聚合后的表体列表
    """
    if not results:
        return []
    
    # 找出最大商品数量
    max_products = max(len(result.pre_dec_list) for result in results)
    
    aggregated_list = []
    
    for product_idx in range(max_products):
        # 对于每个商品位置，按keyDesc分组
        grouped = defaultdict(list)
        
        for result in results:
            if product_idx < len(result.pre_dec_list):
                product_fields = result.pre_dec_list[product_idx]
                for field in product_fields:
                    grouped[field.key_desc].append({
                        'value': field.value,
                        'pixel': field.pixel,
                        'imageId': field.image_id
                    })
        
        # 转换为列表格式，同时补充key
        product_aggregated = []
        for key_desc, sources in grouped.items():
            # 获取key（在OCR阶段已验证过，这里应能找到）
            key = fuzzy_match_key_desc(key_desc)
            product_aggregated.append({
                'keyDesc': key_desc,
                'key': key,
                'sourceList': sources
            })
        
        aggregated_list.append(product_aggregated)
    
    return aggregated_list


async def check_consistency_and_unify_async(aggregated_data: Dict) -> Dict:
    """
    异步检查各个sourceList中的value是否一致，如果不一致，尝试判断是否为同一含义
    
    Args:
        aggregated_data: 聚合后的数据
        
    Returns:
        处理后的数据
    """
    tasks = []
    
    # 收集所有需要处理的字段
    fields_to_process = []
    
    # 处理表头
    for field in aggregated_data['preDecHead']:
        fields_to_process.append(field['sourceList'])
    
    # 处理表体
    for product_fields in aggregated_data['preDecList']:
        for field in product_fields:
            fields_to_process.append(field['sourceList'])
    
    # 异步处理所有字段
    for source_list in fields_to_process:
        task = unify_source_list_async(source_list)
        tasks.append(task)
    
    # 等待所有任务完成
    await asyncio.gather(*tasks, return_exceptions=True)
    
    return aggregated_data




async def unify_source_list_async(source_list: List[Dict]):
    """
    异步统一sourceList中的value
    如果所有value都一样，不做处理
    如果不一样，调用大模型判断是否为同一含义
    
    Args:
        source_list: 来源列表
    """
    if not source_list:
        return
    
    values = [item['value'] for item in source_list]
    unique_values = set(values)
    
    if len(unique_values) == 1:
        # 所有值一致，不需要处理
        return
    
    # 如果值不一致，调用大模型判断
    logger.info(f"发现不一致的值: {unique_values}，调用大模型判断...")
    
    should_unify, unified_value = await call_llm_to_judge_consistency_async(unique_values)
    
    if should_unify:
        logger.info(f"大模型判断这些值是同一含义，统一为: {unified_value}")
        for item in source_list:
            item['value'] = unified_value
    else:
        logger.warning(f"大模型判断这些值含义不同，保持原样: {unique_values}")


def is_numeric(value: str) -> bool:
    """
    判断字符串是否为纯数值
    
    Args:
        value: 待判断的字符串
        
    Returns:
        是否为纯数值
    """
    if not value:
        return False
    
    # 去除空格和常见的数值分隔符
    cleaned = value.strip().replace(',', '').replace(' ', '')
    
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


async def call_llm_to_judge_consistency_async(values: Set[str]) -> Tuple[bool, str]:
    """
    异步调用大模型判断多个值是否为同一含义
    
    Args:
        values: 需要判断的值集合
        
    Returns:
        (should_unify, unified_value): 是否应该统一，以及统一后的值
    """
    if len(values) <= 1:
        return False, ""
    
    values_list = list(values)
    
    # 如果所有值都是纯数值，先转换为数字进行比较
    all_numeric = all(is_numeric(v) for v in values_list)
    if all_numeric:
        # 转换为数值进行比较
        numeric_values = []
        for v in values_list:
            cleaned = v.strip().replace(',', '').replace(' ', '')
            numeric_values.append(float(cleaned))
        
        # 判断数值是否相等
        unique_numeric = set(numeric_values)
        if len(unique_numeric) == 1:
            # 数值相同，统一为第一个值的格式
            logger.info(f"所有值都是数值且数值相同 {values_list}，统一为第一个值")
            return True, values_list[0]
        else:
            # 数值不同，不统一
            logger.info(f"所有值都是数值但数值不同 {values_list}（转换后：{numeric_values}），判断为不一致")
            return False, ""
    
    # 构建prompt
    prompt = f"""请判断以下这些值是否表示同一含义（例如：不同语言表述、完整名称与缩写、不同格式等）：

值列表：
{json.dumps(values_list, ensure_ascii=False, indent=2)}

判断规则：
1. 如果这些值在语义上是相同的（如"montreal"和"蒙特利尔"、"USA"和"美国"、"CANIMEX INC."和"Buyer买方CANIMEX INC."），返回true
2. 如果这些值表示不同的含义，返回false
3. 如果判断为true，需要选择一个最合适的值作为统一值（通常选择最完整、最规范的表述）

请严格按照以下JSON格式返回（不要添加markdown标记）：
{{
  "should_unify": true或false,
  "unified_value": "统一后的值（如果should_unify为false则为空字符串）",
  "reason": "判断理由"
}}
"""
    
    try:
        client = AsyncOpenAI(
            api_key=settings.API_KEY,
            base_url=settings.API_BASE_URL
        )
        
        # 最多重试3次
        for attempt in range(settings.MAX_RETRIES):
            try:
                # 使用文本模型（qwen-flash）进行快速判断
                completion = await client.chat.completions.create(
                    model=settings.TEXT_MODEL_NAME,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )
                
                response_text = completion.choices[0].message.content
                logger.debug(f"大模型返回: {response_text}")
                
                # 解析JSON
                # 移除可能的markdown标记
                cleaned = response_text.strip()
                if cleaned.startswith('```json'):
                    cleaned = cleaned[7:]
                if cleaned.startswith('```'):
                    cleaned = cleaned[3:]
                if cleaned.endswith('```'):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
                
                result = json.loads(cleaned)
                
                should_unify = result.get('should_unify', False)
                unified_value = result.get('unified_value', '')
                reason = result.get('reason', '')
                
                logger.info(f"判断结果: should_unify={should_unify}, unified_value={unified_value}, reason={reason}")
                
                return should_unify, unified_value
                
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失败 (尝试 {attempt + 1}/{settings.MAX_RETRIES}): {str(e)}")
                if attempt == settings.MAX_RETRIES - 1:
                    logger.error("达到最大重试次数，放弃判断")
                    return False, ""
            except Exception as e:
                logger.error(f"调用大模型判断时发生错误: {str(e)}")
                if attempt == settings.MAX_RETRIES - 1:
                    return False, ""
        
        return False, ""
        
    except Exception as e:
        logger.error(f"调用大模型判断失败: {str(e)}")
        return False, ""


def aggregate_mainfactors(data, factor_list):
    """
    将申报要素合并到 preDecList 中。
    严格保证字典 Key 的顺序：
    外层: keyDesc -> key -> sourceList
    内层: value -> pixel -> imageId
    """
    # 1. 建立映射字典
    factors_map = {item['codeTs']: item for item in factor_list}
    
    pre_dec_list = data.get('preDecList', [])

    for item_list in pre_dec_list:
        current_code_ts = None
        
        # 2. 获取当前商品的 codeTs
        for field in item_list:
            if field.get('key') == 'codeTs':
                source_list = field.get('sourceList', [{}])
                if source_list:
                    current_code_ts = source_list[0].get('value')
                break
        
        # 3. 如果匹配到申报要素，构造符合顺序的新字典
        if current_code_ts and current_code_ts in factors_map:
            target_factor = factors_map[current_code_ts]
            
            # --- 步骤 A: 构建内层字典 (按照 value -> pixel -> imageId 顺序) ---
            new_source_item = {
                'value': target_factor['mainfactors'],
                'pixel': target_factor['pixel'],
                'imageId': target_factor['imageId']
            }
            
            # --- 步骤 B: 构建外层字典 (按照 keyDesc -> key -> sourceList 顺序) ---
            # 注意：如果原数据中 gModel 的 keyDesc 叫其他名字（极少见），这里统一重置为 '规格型号'
            new_gmodel_field = {
                'keyDesc': '规格型号',
                'key': 'gModel',
                'sourceList': [new_source_item]
            }

            # --- 步骤 C: 替换或追加 ---
            gmodel_index = -1
            for i, field in enumerate(item_list):
                if field.get('key') == 'gModel':
                    gmodel_index = i
                    break
            
            if gmodel_index != -1:
                # 如果存在，直接替换整个字典对象，以保证 Key 的顺序完全重置
                item_list[gmodel_index] = new_gmodel_field
            else:
                # 如果不存在，追加到末尾
                item_list.append(new_gmodel_field)

    return data