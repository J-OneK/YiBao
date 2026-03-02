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
from .image_preprocessor import preprocess_image

# 不去除空格的字段白名单（中文字段名 key_desc）
_NO_STRIP_KEYS = {
    # 用户明确指定的字段
    "境外收发货人", "存放地点", "标记唛码及备注", "商品名称", "规格型号",
    # 需要代码映射的字段
    "运抵国", "贸易国", "原产国", "最终目的国",
    "指运港", "离境口岸",
    "运输方式", "监管方式", "成交方式",
    "征免性质", "征免", "征减免税方式",
    "包装种类",
    "运费币制", "保费币制", "成交币制", "杂费币制", "币制",
    "运费标记", "保费标记", "杂费标记",
    "境内货源地", "成交单位", "成交计量单位",
}


def _strip_spaces(value: str, key_desc: str) -> str:
    """对字段值去除所有空格，白名单字段跳过"""
    if key_desc in _NO_STRIP_KEYS:
        return value
    return value.replace(" ", "")

# 配置日志
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)

_CLIENT = None


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = AsyncOpenAI(
            api_key=settings.API_KEY,
            base_url=settings.API_BASE_URL
        )
    return _CLIENT


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
    client = _get_client()
    
    # 图片预处理：检测方向并旋转
    preprocessed_url, rotation_angle, final_width, final_height = preprocess_image(image_info.image_url)
    
    # 使用预处理后的 URL（OSS URL 或 base64 URL），失败则回退到原始 URL
    if preprocessed_url:
        actual_image_url = preprocessed_url
        image_info.angle = rotation_angle
        image_info.width = final_width
        image_info.height = final_height
        
        # 如果返回的是OSS URL（非base64），更新image_info中的原始URL
        if not preprocessed_url.startswith('data:'):
            image_info.image_url = preprocessed_url
            logger.info(f"图片 {image_info.image_id} 预处理完成，旋转 {rotation_angle} 度，已上传到OSS")
        else:
            logger.info(f"图片 {image_info.image_id} 预处理完成，旋转 {rotation_angle} 度，使用base64格式")
    else:
        actual_image_url = image_info.image_url
        logger.debug(f"图片 {image_info.image_id} 使用原始 URL")
    
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
                                "image_url": {"url": actual_image_url}
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
        print(f'<<{key_desc}>>')
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
            value=_strip_spaces(str(item['value']), key_desc),
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
                value=_strip_spaces(str(item['value']), key_desc),
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


async def recognize_image_async_no_preprocess(image_info: ImageInfo, prompt: str, is_mainfactor: bool) -> Optional[ExtractionResult]:
    """
    异步识别单张图片（不进行预处理，直接使用已有URL）
    用于第二次调用大模型时，复用第一次已处理好的图片
    
    特殊处理：如果 att_type_code=5，说明这张图片是第一次处理，需要执行预处理
    
    Args:
        image_info: 图片信息（应包含已处理的OSS URL）
        prompt: 识别prompt
        is_mainfactor: 是否是申报要素识别
        
    Returns:
        提取结果，失败返回None
    """
    client = _get_client()
    
    # 检查是否需要预处理（att_type_code=5是第一次处理）
    if image_info.att_type_code == 5:
        logger.info(f"图片 {image_info.image_id} (att_type_code=5) 首次处理，执行预处理")
        # 执行图片预处理（旋转矫正 + OSS上传）
        preprocessed_url, rotation_angle, final_width, final_height = preprocess_image(image_info.image_url)
        
        # 使用预处理后的 URL（OSS URL 或 base64 URL），失败则回退到原始 URL
        if preprocessed_url:
            actual_image_url = preprocessed_url
            image_info.angle = rotation_angle
            image_info.width = final_width
            image_info.height = final_height
            
            # 如果返回的是OSS URL（非base64），更新image_info中的原始URL
            if not preprocessed_url.startswith('data:'):
                image_info.image_url = preprocessed_url
                logger.info(f"图片 {image_info.image_id} 预处理完成，旋转 {rotation_angle} 度，已上传到OSS")
            else:
                logger.info(f"图片 {image_info.image_id} 预处理完成，旋转 {rotation_angle} 度，使用base64格式")
        else:
            actual_image_url = image_info.image_url
            logger.debug(f"图片 {image_info.image_id} 预处理失败，使用原始 URL")
    else:
        # 直接使用image_info中的URL，不进行预处理
        actual_image_url = image_info.image_url
        logger.debug(f"图片 {image_info.image_id} 使用已处理的URL（跳过预处理）")
    
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
                                "image_url": {"url": actual_image_url}
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


async def recognize_images_batch_no_preprocess(image_infos: List[ImageInfo], prompts: List[str], is_mainfactor: bool) -> List[Optional[ExtractionResult]]:
    """
    批量异步识别多张图片（不进行预处理）
    用于第二次调用大模型时，复用第一次已处理好的图片
    
    Args:
        image_infos: 图片信息列表
        prompts: 对应的prompt列表
        is_mainfactor: 是否是申报要素识别
        
    Returns:
        识别结果列表
    """
    if len(image_infos) != len(prompts):
        raise ValueError("图片数量和prompt数量不匹配")
    
    # 创建所有异步任务
    tasks = [
        recognize_image_async_no_preprocess(img_info, prompt, is_mainfactor)
        for img_info, prompt in zip(image_infos, prompts)
    ]
    
    # 并发执行所有任务
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理异常结果
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"图片 {image_infos[i].image_id} 识别出现异常: {str(result)}")
            processed_results.append(None)
        else:
            processed_results.append(result)
    
    return processed_results
