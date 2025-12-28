"""
OCR 服务模块
调用视觉大模型API进行图片识别
支持异步并发处理
"""
import logging
import asyncio
from openai import AsyncOpenAI
from typing import Optional, List
from config import settings
from config.field_mapping import fuzzy_match_key_desc, is_valid_source
from .models import ImageInfo, ExtractionResult, ExtractedField
from . import json_utils

# 配置日志
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)


async def recognize_images_batch(image_infos: List[ImageInfo], prompts: List[str], is_mainfactor: bool) -> List[Optional[ExtractionResult]]:
    """
    批量异步识别多张图片
    
    Args:
        image_infos: 图片信息列表
        prompts: 对应的prompt列表
        
    Returns:
        识别结果列表
    """
    tasks = []
    for image_info, prompt in zip(image_infos, prompts):
        task = recognize_image_async(image_info, prompt, is_mainfactor)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理主申报要素识别结果
    if is_mainfactor:
        return [result for result in results if result is not None]

    # 处理异常结果
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"图片 {image_infos[i].image_id} 识别失败: {str(result)}")
            processed_results.append(None)
        else:
            processed_results.append(result)
    
    return processed_results


async def recognize_image_async(image_info: ImageInfo, prompt: str, is_mainfactor: bool) -> Optional[ExtractionResult]:
    """
    异步识别单张图片
    
    Args:
        image_info: 图片信息
        prompt: 识别prompt
        
    Returns:
        提取结果，失败返回None
    """
    client = AsyncOpenAI(
        api_key=settings.API_KEY,
        base_url=settings.API_BASE_URL
    )
    
    # 最多重试3次
    for attempt in range(settings.MAX_RETRIES):
        try:
            logger.info(f"正在识别图片 {image_info.image_id}，第 {attempt + 1} 次尝试")
            
            # 构造API请求
            completion = await client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": image_info.image_url}
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )
            
            # 获取返回的文本
            response_text = completion.choices[0].message.content
            logger.debug(f"模型返回: {response_text[:200]}...")

            # 解析JSON
            if is_mainfactor:
                parsed_data = json_utils.parse_mainfactor_json(response_text)
                for item in parsed_data['gmodel']:
                    item['imageId'] = image_info.image_id
                    item['attTypeCode'] = image_info.att_type_code
            else:
                parsed_data = json_utils.parse_and_validate(response_text)

            if parsed_data is None:
                logger.warning(f"JSON解析失败，第 {attempt + 1} 次尝试")
                if attempt < settings.MAX_RETRIES - 1:
                    continue
                else:
                    logger.error(f"图片 {image_info.image_id} 识别失败，已达最大重试次数")
                    return None
            
            if is_mainfactor:
                # 如果是申报要素识别，直接返回结果
                return parsed_data

            # 转换为ExtractionResult对象，同时进行字段映射和过滤
            result = convert_to_extraction_result(
                parsed_data,
                image_info.image_id,
                image_info.att_type_code
            )
            logger.info(f"图片 {image_info.image_id} 识别成功")
            return result
            
        except Exception as e:
            logger.error(f"识别图片 {image_info.image_id} 时发生错误: {str(e)}")
            if attempt < settings.MAX_RETRIES - 1:
                continue
            else:
                return None
    
    return None


def convert_to_extraction_result(data: dict, image_id: str, att_type_code: int) -> ExtractionResult:
    """
    将解析后的字典转换为ExtractionResult对象
    同时进行字段映射和过滤（删除key为空或来源无效的字段）
    
    Args:
        data: 解析后的数据字典
        image_id: 图片ID
        att_type_code: 文件类型代码
        
    Returns:
        ExtractionResult对象
    """
    # 转换preDecHead
    pre_dec_head = []
    for item in data.get('preDecHead', []):
        key_desc = item['keyDesc']
        # 模糊匹配获取key
        key = fuzzy_match_key_desc(key_desc)
        
        # 如果key为空，跳过
        if not key:
            logger.warning(f"字段 {key_desc} 模糊匹配失败，已跳过")
            continue
        
        # 检查该字段从此文件类型识别是否有效
        if not is_valid_source(key, att_type_code, 'head'):
            logger.warning(f"字段 {key_desc}(key={key}) 不应从文件类型 {att_type_code} 的表头中识别，已跳过")
            continue
        
        field = ExtractedField(
            key_desc=key_desc,
            value=str(item['value']),
            pixel=item['pixel'],
            image_id=image_id,
            att_type_code=att_type_code
        )
        pre_dec_head.append(field)
    
    # 转换preDecList
    pre_dec_list = []
    for product_fields in data.get('preDecList', []):
        product = []
        for item in product_fields:
            key_desc = item['keyDesc']
            # 模糊匹配获取key
            key = fuzzy_match_key_desc(key_desc)
            
            # 如果key为空，跳过
            if not key:
                logger.warning(f"字段 {key_desc} 模糊匹配失败，已跳过")
                continue
            
            # 检查该字段从此文件类型识别是否有效
            if not is_valid_source(key, att_type_code, 'list'):
                logger.warning(f"字段 {key_desc}(key={key}) 不应从文件类型 {att_type_code} 的表体中识别，已跳过")
                continue
            
            field = ExtractedField(
                key_desc=key_desc,
                value=str(item['value']),
                pixel=item['pixel'],
                image_id=image_id,
                att_type_code=att_type_code
            )
            product.append(field)
        
        # 只添加非空的商品
        if product:
            pre_dec_list.append(product)
    
    return ExtractionResult(
        pre_dec_head=pre_dec_head,
        pre_dec_list=pre_dec_list,
        image_id=image_id
    )
