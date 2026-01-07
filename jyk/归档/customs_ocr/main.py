"""
报关文档识别系统 - 主程序入口
支持异步并发处理
"""
import json
import logging
import sys
import asyncio
from pathlib import Path

from core.data_loader import load_input_data
from core.prompt_manager import generate_prompt, generate_mainfactor_prompt
from core.ocr_service import recognize_images_batch
from core.aggregator import aggregate_results, check_consistency_and_unify_async, aggregate_mainfactors
from core.post_processor import process_final_output, process_mainfactors, transform_final_output
from config import settings
from core.mainfactor_utils import get_codets_values, normalize_values, get_mainfactor

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

total_steps = 7


async def main_async(input_json_path: str, output_json_path: str):
    """
    异步主函数
    
    Args:
        input_json_path: 输入JSON文件路径
        output_json_path: 输出JSON文件路径
    """
    try:
        logger.info("=" * 60)
        logger.info("报关文档识别系统启动（异步并发模式）")
        logger.info("=" * 60)
        
        # 1. 加载输入数据
        logger.info(f"步骤 1/{total_steps}: 加载输入数据...")
        image_infos, operate_images = load_input_data(input_json_path)
        logger.info(f"成功加载 {len(image_infos)} 张图片信息")
        
        # 2. 并发识别所有图片
        logger.info(f"步骤 2/{total_steps}: 并发调用视觉大模型识别图片...")
        prompts = [generate_prompt(img.att_type_code) for img in image_infos]
        results = await recognize_images_batch(image_infos, prompts, is_mainfactor=False)

        # 过滤掉识别失败的结果
        valid_results = [r for r in results if r is not None]
        
        if not valid_results:
            logger.error("所有图片识别失败，程序终止")
            return
        
        logger.info(f"成功识别 {len(valid_results)}/{len(image_infos)} 张图片")

        # print(f"未处理结果：{valid_results}")
        
        # 3. 聚合多图片识别结果
        logger.info(f"步骤 3/{total_steps}: 聚合多图片识别结果...")
        aggregated_data = aggregate_results(valid_results)
        logger.info("聚合完成")
        
        print(f"聚合结果：{aggregated_data}")

        # 4. 根据聚合结果提取商品编号识别申报要素
        logger.info(f"步骤 4/{total_steps}: 并发调用视觉大模型识别图片...")
        hsCodes = normalize_values(get_codets_values(aggregated_data))
        if not hsCodes:
            logger.error("未能从输入文件中提取到任何商品编号，程序终止")
            return
        mainfactors = []
        logger.info(f"提取到 {len(hsCodes)} 个商品编号，分别是：{hsCodes}")
        for hs in hsCodes:
            mainfactor = get_mainfactor(hs)
            mainfactors.append(mainfactor)
        mainfactors = [mainfactor for mainfactor in mainfactors if mainfactor]
        logger.info(f"成功提取 {len(mainfactors)} 个申报要素，分别是：{mainfactors}")

        prompts = [generate_mainfactor_prompt(hsCodes, mainfactors) for i in range(len(image_infos))]
        results = await recognize_images_batch(image_infos, prompts, is_mainfactor=True)

        # 过滤掉识别失败的结果
        valid_results = [r for r in results if r is not None]
        print(f"未处理结果：{valid_results}")
        # 处理申报要素识别结果
        valid_results = process_mainfactors(valid_results)

        print(f"申报要素识别结果：{valid_results}")

        logger.info("聚合申报要素识别结果")
        aggregated_data = aggregate_mainfactors(aggregated_data, valid_results)
        logger.info("聚合申报要素识别结果完成")
        
        # 5. 异步检查一致性并统一
        logger.info(f"步骤 5/{total_steps}: 并发检查字段一致性...")
        aggregated_data = await check_consistency_and_unify_async(aggregated_data)
        logger.info("一致性检查完成")

        # 6. 后处理：生成parsedValue、坐标转换
        logger.info(f"步骤 6/{total_steps}: 后处理（生成parsedValue、坐标转换）...")
        final_output = process_final_output(aggregated_data, image_infos)
        logger.info("后处理完成")
        
        # 7. 转换成OCR.json格式
        logger.info(f"步骤 7/{total_steps}: 转换成OCR.json格式...")
        final_output = transform_final_output(final_output, operate_images)
        logger.info("转换完成")

        # 8. 保存结果
        logger.info(f"保存结果到 {output_json_path}...")
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)
        logger.info("结果保存成功")
        
        logger.info("=" * 60)
        logger.info("报关文档识别系统完成")
        logger.info("=" * 60)
        
        # 输出统计信息
        head_count = len(final_output.get('preDecHead', []))
        list_count = len(final_output.get('preDecList', []))
        logger.info(f"识别结果统计：")
        logger.info(f"  表头字段数: {head_count}")
        logger.info(f"  商品数量: {list_count}")
        
    except Exception as e:
        logger.error(f"程序执行出错: {str(e)}", exc_info=True)
        sys.exit(1)

async def main_factor_async(input_json_path: str, output_json_path: str, OCR_json_path: str):
    """
    异步申报要素主函数
    
    Args:
        input_json_path: 输入JSON文件路径
        output_json_path: 输出JSON文件路径
    """
    try:
        logger.info("=" * 60)
        logger.info("报关文档申报要素识别启动（异步并发模式）")
        logger.info("=" * 60)
        
        # 前置：提取申报要素字段
        hsCodes = normalize_values(get_codets_values(input_json_path))
        if not hsCodes:
            logger.error("未能从输入文件中提取到任何商品编号，程序终止")
            return
        mainfactors = []
        logger.info(f"提取到 {len(hsCodes)} 个商品编号，分别是：{hsCodes}")
        for hs in hsCodes:
            mainfactor = get_mainfactor(hs)
            mainfactors.append(mainfactor)
        mainfactors = [mainfactor for mainfactor in mainfactors if mainfactor]
        logger.info(f"成功提取 {len(mainfactors)} 个申报要素，分别是：{mainfactors}")

        # 1. 加载输入数据
        logger.info("步骤 1/5: 加载输入数据...")
        image_infos = load_input_data(OCR_json_path)
        logger.info(f"成功加载 {len(image_infos)} 张图片信息")
        
        # 2. 并发识别所有图片
        logger.info("步骤 2/5: 并发调用视觉大模型识别图片...")
        prompts = [generate_mainfactor_prompt(hsCodes, mainfactors) for i in range(len(image_infos))]
        results = await recognize_images_batch(image_infos, prompts, is_mainfactor=True)

        # 过滤掉识别失败的结果
        valid_results = [r for r in results if r is not None]
        print(f"未处理结果：{valid_results}")
        # 处理申报要素识别结果
        valid_results = process_mainfactors(valid_results)
        
        logger.info(f"成功识别 {len(valid_results)}/{len(image_infos)} 张图片")

        print(f"识别结果：{valid_results}")

        
        # 保存结果
        logger.info(f"保存结果到 {output_json_path}...")
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(valid_results, f, ensure_ascii=False, indent=2)
        logger.info("结果保存成功")
        
    except Exception as e:
        logger.error(f"程序执行出错: {str(e)}", exc_info=True)
        sys.exit(1)

def main(input_json_path: str, output_json_path: str):
    """
    主函数（同步包装器）
    
    Args:
        input_json_path: 输入JSON文件路径
        output_json_path: 输出JSON文件路径
        OCR_json_path: OCR JSON文件路径
    """
    asyncio.run(main_async(input_json_path, output_json_path))
    # asyncio.run(main_factor_async(input_json_path, output_json_path, OCR_json_path))


if __name__ == "__main__":
    # 默认路径
    input_path = "/Users/1k/code/YiBao/jyk/归档/customs_ocr/OCR识别报文.json"
    output_path = "/Users/1k/code/YiBao/jyk/归档/customs_ocr/output_result.json"

    # 如果提供了命令行参数，使用命令行参数
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    
    # 检查输入文件是否存在
    if not Path(input_path).exists():
        logger.error(f"输入文件不存在: {input_path}")
        logger.info("用法: python main.py [输入JSON路径] [输出JSON路径]")
        sys.exit(1)

    main(input_path, output_path)
