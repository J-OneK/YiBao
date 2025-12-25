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
from core.prompt_manager import generate_prompt
from core.ocr_service import recognize_images_batch
from core.aggregator import aggregate_results, check_consistency_and_unify_async
from core.post_processor import process_final_output
from config import settings

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
        logger.info("步骤 1/5: 加载输入数据...")
        image_infos = load_input_data(input_json_path)
        logger.info(f"成功加载 {len(image_infos)} 张图片信息")
        
        # 2. 并发识别所有图片
        logger.info("步骤 2/5: 并发调用视觉大模型识别图片...")
        prompts = [generate_prompt(img.att_type_code) for img in image_infos]
        results = await recognize_images_batch(image_infos, prompts)
        
        # 过滤掉识别失败的结果
        valid_results = [r for r in results if r is not None]
        
        if not valid_results:
            logger.error("所有图片识别失败，程序终止")
            return
        
        logger.info(f"成功识别 {len(valid_results)}/{len(image_infos)} 张图片")
        
        # 3. 聚合多图片识别结果
        logger.info("步骤 3/5: 聚合多图片识别结果...")
        aggregated_data = aggregate_results(valid_results)
        logger.info("聚合完成")
        
        # 4. 异步检查一致性并统一
        logger.info("步骤 4/5: 并发检查字段一致性...")
        aggregated_data = await check_consistency_and_unify_async(aggregated_data)
        logger.info("一致性检查完成")
        
        # 5. 后处理：生成parsedValue、坐标转换
        logger.info("步骤 5/5: 后处理（生成parsedValue、坐标转换）...")
        final_output = process_final_output(aggregated_data, image_infos)
        logger.info("后处理完成")
        
        # 6.映射

        # 7.申报要素

        # 8.转为ocr.json格式




        # 6. 保存结果
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


def main(input_json_path: str, output_json_path: str):
    """
    主函数（同步包装器）
    
    Args:
        input_json_path: 输入JSON文件路径
        output_json_path: 输出JSON文件路径
    """
    asyncio.run(main_async(input_json_path, output_json_path))


if __name__ == "__main__":
    # 默认路径
    input_path = "../OCR识别报文.json"
    output_path = "./output_result.json"
    
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
