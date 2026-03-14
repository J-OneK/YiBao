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


# 海关代码字段：必须为 10 位数字或字母
_CODE_10_KEYS = {"境内收发货人海关代码", "生产销售单位海关代码"}
# 社会信用代码字段：必须为 18 位数字或字母
_CODE_18_KEYS = {"境内收发货人社会信用代码", "生产销售单位社会信用代码"}


def _validate_code(value: str, key_desc: str) -> str:
    """对代码类字段做长度校验，不符合格式则返回空字符串"""
    if key_desc in _CODE_10_KEYS:
        if len(value) == 10 and value.isalnum():
            return value
        print(f'{key_desc} 代码长度有误："{value}"（长度={len(value)}，期望10位字母数字），输出空')
        return ""
    if key_desc in _CODE_18_KEYS:
        if len(value) == 18 and value.isalnum():
            return value
        print(f'{key_desc} 代码长度有误："{value}"（长度={len(value)}，期望18位字母数字），输出空')
        return ""
    return value

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
        prompts: 对应的prompt列表（同一 att_type_code 的图片 prompt 是相同的）
        
    Returns:
        识别结果列表，与 image_infos 原序对应
    """
    # 按 att_type_code 分组
    from collections import defaultdict
    groups = defaultdict(list)
    
    # 记录原始索引，以便组装最后结果
    for i, (img_info, prompt) in enumerate(zip(image_infos, prompts)):
        groups[img_info.att_type_code].append({
            "index": i,
            "image_info": img_info,
            "prompt": prompt
        })
        
    tasks = []
    # 存储分组识别结果的 Promise 回调信息
    group_promises = []
    
    for att_type, items in groups.items():
        # 同组图片提取为列表
        group_image_infos = [item["image_info"] for item in items]
        # 同组 prompt 取第一个即可
        group_prompt = items[0]["prompt"]
        
        task = recognize_grouped_images_async(group_image_infos, group_prompt, is_mainfactor)
        tasks.append(task)
        group_promises.append(items)
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 构建与 image_infos 等长的返回值列表
    final_results = [None] * len(image_infos)
    
    for i, group_result in enumerate(results):
        items = group_promises[i]
        
        if isinstance(group_result, Exception):
            logger.error(f"分组 {items[0]['image_info'].att_type_code} 识别出现异常: {str(group_result)}")
            for item in items:
                 final_results[item["index"]] = None
        else:
            # group_result 是 List[ExtractionResult]
            if not group_result:
                 for item in items:
                     final_results[item["index"]] = None
                 continue

            # 通过 image_id 将结果映射回原顺序
            result_map = {}
            for res in group_result:
                if res:
                    res_img_id = res['image_id'] if isinstance(res, dict) else res.image_id
                    result_map[res_img_id] = res
            
            for item in items:
                img_id = item["image_info"].image_id
                final_results[item["index"]] = result_map.get(img_id, None)

    # 兼容历史行为，如果是 is_mainfactor 则过滤掉 None
    if is_mainfactor:
        return [res for res in final_results if res is not None]
        
    return final_results


async def recognize_grouped_images_async(image_infos: List[ImageInfo], prompt: str, is_mainfactor: bool) -> List[Optional[ExtractionResult]]:
    """
    异步识别同组的多张图片
    
    Args:
        image_infos: 同组图片信息列表
        prompt: 识别prompt
        is_mainfactor: 是否为申报要素
        
    Returns:
        该组提取结果列表，失败返回空列表或包含 None
    """
    if not image_infos:
        return []
        
    client = _get_client()
    
    content_list = []
    image_mapping_texts = []
    
    for i, image_info in enumerate(image_infos):
        # 图片预处理：检测方向并旋转
        preprocessed_url, rotation_angle, final_width, final_height = preprocess_image(image_info.image_url)
        
        if preprocessed_url:
            actual_image_url = preprocessed_url
            image_info.angle = rotation_angle
            image_info.width = final_width
            image_info.height = final_height
            
            if not preprocessed_url.startswith('data:'):
                image_info.image_url = preprocessed_url
                logger.info(f"图片 {image_info.image_id} 预处理完成，旋转 {rotation_angle} 度，已上传到OSS")
            else:
                logger.info(f"图片 {image_info.image_id} 预处理完成，旋转 {rotation_angle} 度，使用base64格式")
        else:
            actual_image_url = image_info.image_url
            logger.debug(f"图片 {image_info.image_id} 预处理失败，使用原始 URL")
            
        url_for_prompt = actual_image_url if not actual_image_url.startswith('data:') else "base64_data..."
        image_mapping_texts.append(f"第 {i+1} 张图片: image_id='{image_info.image_id}', url='{url_for_prompt}'")
        
        content_list.append({
            "type": "text",
            "text": f"--- 以下是第 {i+1} 张图片 (image_id: {image_info.image_id}) ---"
        })
        content_list.append({
            "type": "image_url",
            "image_url": {"url": actual_image_url}
        })
        
    # 添加 prompt 文本
    mapping_str = "\\n".join(image_mapping_texts)
    prompt_with_ids = f"我们需要识别以下 {len(image_infos)} 张图片。图片与其 image_id 和 url 的对应关系如下：\\n{mapping_str}\\n\\n请严格使用上述 image_id 区分返回结果。\\n\\n" + prompt
    
    content_list.append({
        "type": "text",
        "text": prompt_with_ids
    })
    
    # 最多重试3次
    for attempt in range(settings.MAX_RETRIES):
        try:
            logger.info(f"正在批量识别一组图片（组大小: {len(image_infos)}, 类型: {image_infos[0].att_type_code}），第 {attempt + 1} 次尝试")
            
            completion = await client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": content_list
                    }
                ]
            )
            
            response_text = completion.choices[0].message.content
            logger.debug(f"模型返回: {response_text[:200]}...")

            # 解析JSON返回列表类型
            if is_mainfactor:
                parsed_data_list = json_utils.parse_mainfactor_json(response_text)
            else:
                parsed_data_list = json_utils.parse_and_validate(response_text)

            if parsed_data_list is None:
                logger.warning(f"JSON解析失败，第 {attempt + 1} 次尝试")
                if attempt < settings.MAX_RETRIES - 1:
                    continue
                else:
                    logger.error("批量识别失败，已达最大重试次数")
                    return []
            
            # 分发结果
            results = []
            att_type_code = image_infos[0].att_type_code
            
            # 申报要素目前是 gmodel 的结构，里面包含具体商品。这里适配历史主流程中的数据装配：
            if is_mainfactor:
                 for partitioned_data in parsed_data_list:
                     # 此时 partitioned_data 是个包含 gmodel 以及 image_id 的单项
                     image_id = partitioned_data.get('image_id')
                     
                     # 适配：给内部每个项补全 imageId 和 attTypeCode (由于 json_utils 解析有可能已剥掉外层)
                     if 'gmodel' in partitioned_data:
                         items_to_modify = partitioned_data['gmodel']
                     else:
                         # 支持 json_utils 退阶剥落的场景或者只有对象自身的情况
                         items_to_modify = [partitioned_data] if isinstance(partitioned_data, dict) else partitioned_data
                     
                     if isinstance(items_to_modify, list):
                         for item in items_to_modify:
                             item['imageId'] = image_id
                             item['attTypeCode'] = att_type_code
                     results.append(partitioned_data)
                 return results
                 
            for partitioned_data in parsed_data_list:
                image_id = str(partitioned_data.get('image_id', ''))
                # 转换为ExtractionResult对象，同时进行字段映射和过滤
                result = convert_to_extraction_result(
                    partitioned_data,
                    image_id,
                    att_type_code
                )
                results.append(result)
                
            logger.info("批量图片识别成功")
            return results
            
        except Exception as e:
            logger.error(f"批量识别图片时发生错误: {str(e)}")
            if attempt < settings.MAX_RETRIES - 1:
                continue
            else:
                return []
    
    return []


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
            value=_validate_code(_strip_spaces(str(item['value']), key_desc), key_desc),
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
                value=_validate_code(_strip_spaces(str(item['value']), key_desc), key_desc),
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


async def recognize_grouped_images_async_no_preprocess(image_infos: List[ImageInfo], prompt: str, is_mainfactor: bool) -> List[Optional[ExtractionResult]]:
    """
    异步识别同组多张图片（不进行预处理，直接使用已有URL）
    用于第二次调用大模型时，复用第一次已处理好的图片
    
    特殊处理：如果 att_type_code=5，说明这张图片是第一次处理，需要执行预处理
    
    Args:
        image_infos: 同组图片信息列表
        prompt: 识别prompt
        is_mainfactor: 是否是申报要素识别
        
    Returns:
        提取结果列表，失败返回空列表或包含 None
    """
    if not image_infos:
        return []
        
    client = _get_client()
    
    content_list = []
    image_mapping_texts = []
    
    for i, image_info in enumerate(image_infos):
        # 检查是否需要预处理（att_type_code=5是第一次处理）
        if image_info.att_type_code == 5:
            logger.info(f"图片 {image_info.image_id} (att_type_code=5) 首次处理，执行预处理")
            preprocessed_url, rotation_angle, final_width, final_height = preprocess_image(image_info.image_url)
            
            if preprocessed_url:
                actual_image_url = preprocessed_url
                image_info.angle = rotation_angle
                image_info.width = final_width
                image_info.height = final_height
                
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
            
        url_for_prompt = actual_image_url if not actual_image_url.startswith('data:') else "base64_data..."
        image_mapping_texts.append(f"第 {i+1} 张图片: image_id='{image_info.image_id}', url='{url_for_prompt}'")
        
        content_list.append({
            "type": "text",
            "text": f"--- 以下是第 {i+1} 张图片 (image_id: {image_info.image_id}) ---"
        })
        content_list.append({
            "type": "image_url",
            "image_url": {"url": actual_image_url}
        })
        
    mapping_str = "\\n".join(image_mapping_texts)
    prompt_with_ids = f"我们需要识别以下 {len(image_infos)} 张图片。图片与其 image_id 和 url 的对应关系如下：\\n{mapping_str}\\n\\n请严格使用上述 image_id 区分返回结果。\\n\\n" + prompt
    
    content_list.append({
        "type": "text",
        "text": prompt_with_ids
    })
    
    # 最多重试3次
    for attempt in range(settings.MAX_RETRIES):
        try:
            logger.info(f"正在批量识别一组图片(无预处理)（组大小: {len(image_infos)}, 类型: {image_infos[0].att_type_code}），第 {attempt + 1} 次尝试")
            
            completion = await client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": content_list
                    }
                ]
            )
            
            response_text = completion.choices[0].message.content
            logger.debug(f"模型返回: {response_text[:200]}...")

            # 解析JSON
            if is_mainfactor:
                parsed_data_list = json_utils.parse_mainfactor_json(response_text)
            else:
                parsed_data_list = json_utils.parse_and_validate(response_text)

            if parsed_data_list is None:
                logger.warning(f"JSON解析失败，第 {attempt + 1} 次尝试")
                if attempt < settings.MAX_RETRIES - 1:
                    continue
                else:
                    logger.error("无预处理批量识别失败，已达最大重试次数")
                    return []
            
            # 分发结果
            results = []
            att_type_code = image_infos[0].att_type_code
            
            if is_mainfactor:
                 for partitioned_data in parsed_data_list:
                     image_id = partitioned_data.get('image_id')
                     if 'gmodel' in partitioned_data:
                         items_to_modify = partitioned_data['gmodel']
                     else:
                         items_to_modify = [partitioned_data] if isinstance(partitioned_data, dict) else partitioned_data
                         
                     if isinstance(items_to_modify, list):
                         for item in items_to_modify:
                             item['imageId'] = image_id
                             item['attTypeCode'] = att_type_code
                     results.append(partitioned_data)
                 return results

            for partitioned_data in parsed_data_list:
                image_id = str(partitioned_data.get('image_id', ''))
                result = convert_to_extraction_result(
                    partitioned_data,
                    image_id,
                    att_type_code
                )
                results.append(result)
                
            logger.info("无预处理批量图片识别成功")
            return results
            
        except Exception as e:
            logger.error(f"无预处理批量识别图片时发生错误: {str(e)}")
            if attempt < settings.MAX_RETRIES - 1:
                continue
            else:
                return []
    
    return []


async def recognize_images_batch_no_preprocess(image_infos: List[ImageInfo], prompts: List[str], is_mainfactor: bool) -> List[Optional[ExtractionResult]]:
    """
    批量异步识别多张图片（不进行预处理）
    用于第二次调用大模型时，复用第一次已处理好的图片
    
    Args:
        image_infos: 图片信息列表
        prompts: 对应的prompt列表
        is_mainfactor: 是否是申报要素识别
        
    Returns:
        识别结果列表，与 image_infos 原序对应
    """
    if len(image_infos) != len(prompts):
        raise ValueError("图片数量和prompt数量不匹配")
    
    # 按 att_type_code 分组
    from collections import defaultdict
    groups = defaultdict(list)
    
    for i, (img_info, prompt) in enumerate(zip(image_infos, prompts)):
        groups[img_info.att_type_code].append({
            "index": i,
            "image_info": img_info,
            "prompt": prompt
        })
        
    tasks = []
    group_promises = []
    
    for att_type, items in groups.items():
        group_image_infos = [item["image_info"] for item in items]
        group_prompt = items[0]["prompt"]
        
        task = recognize_grouped_images_async_no_preprocess(group_image_infos, group_prompt, is_mainfactor)
        tasks.append(task)
        group_promises.append(items)
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    final_results = [None] * len(image_infos)
    
    for i, group_result in enumerate(results):
        items = group_promises[i]
        
        if isinstance(group_result, Exception):
            logger.error(f"分组 {items[0]['image_info'].att_type_code} (无预处理) 识别出现异常: {str(group_result)}")
            for item in items:
                 final_results[item["index"]] = None
        else:
            if not group_result:
                 for item in items:
                     final_results[item["index"]] = None
                 continue

            result_map = {}
            for res in group_result:
                if res:
                    res_img_id = res['image_id'] if isinstance(res, dict) else res.image_id
                    result_map[res_img_id] = res
            
            for item in items:
                img_id = item["image_info"].image_id
                final_results[item["index"]] = result_map.get(img_id, None)

    return final_results
