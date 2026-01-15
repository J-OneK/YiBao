"""
图片预处理模块 - 使用 TesseractOSD 进行图片方向检测与旋转矫正
"""
import logging
import base64
import io
import re
from typing import Tuple, Optional

import requests
import pytesseract
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)


def load_image_from_url(url: str) -> Optional[Image.Image]:
    """
    从 URL 下载图片并转换为 Pillow Image 对象。
    
    Args:
        url: 图片 URL
        
    Returns:
        Pillow Image 对象，失败返回 None
    """
    try:
        logger.debug(f"正在下载图片: {url}")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        image_bytes = io.BytesIO(response.content)
        img = Image.open(image_bytes)
        logger.debug("图片下载并加载成功")
        return img
    except requests.exceptions.RequestException as e:
        logger.error(f"下载图片时出错: {e}")
        return None
    except Exception as e:
        logger.error(f"打开图片时出错: {e}")
        return None


def detect_and_rotate(img: Image.Image) -> Tuple[Image.Image, int]:
    """
    使用 Tesseract OSD 检测图片方向，并进行旋转校正。
    
    Args:
        img: Pillow Image 对象
        
    Returns:
        (校正后的图片, 旋转角度)
    """
    try:
        logger.debug("正在进行 OSD 方向检测...")
        osd_result_text = pytesseract.image_to_osd(img)
        
        logger.debug(f"Tesseract OSD 输出: {osd_result_text.strip()}")

        # 解析输出结果，找到需要的旋转角度 (Rotate)
        match = re.search(r'Rotate:\s*(\d+)', osd_result_text)
        
        if match:
            rotation_needed_clockwise = int(match.group(1))
        else:
            logger.warning("无法从 OSD 输出中解析出 'Rotate' 值，默认不旋转")
            rotation_needed_clockwise = 0

        logger.debug(f"检测结果：需要顺时针旋转 {rotation_needed_clockwise} 度")

        # 执行旋转
        if rotation_needed_clockwise > 0:
            # Pillow 的 rotate 方法默认是逆时针旋转
            # Tesseract 告诉我们需要顺时针旋转，所以传入负值
            corrected_img = img.rotate(-rotation_needed_clockwise, expand=True)
            logger.info(f"图片已顺时针旋转 {rotation_needed_clockwise} 度")
            return corrected_img, rotation_needed_clockwise
        else:
            logger.debug("图片方向正确，无需旋转")
            return img, 0

    except pytesseract.TesseractError as e:
        logger.warning(f"Tesseract OSD 检测失败: {e}，使用原图")
        return img, 0
    except Exception as e:
        logger.warning(f"方向检测发生未知错误: {e}，使用原图")
        return img, 0


def image_to_base64_url(img: Image.Image, format: str = "PNG") -> str:
    """
    将 Pillow Image 转换为 base64 数据 URL。
    
    Args:
        img: Pillow Image 对象
        format: 图片格式 (PNG, JPEG 等)
        
    Returns:
        base64 数据 URL
    """
    buffer = io.BytesIO()
    
    # 处理 RGBA 图片（PNG 可能包含透明通道）
    if img.mode == 'RGBA' and format.upper() == 'JPEG':
        img = img.convert('RGB')
    
    img.save(buffer, format=format)
    buffer.seek(0)
    
    base64_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
    mime_type = f"image/{format.lower()}"
    
    return f"data:{mime_type};base64,{base64_data}"


def preprocess_image(image_url: str) -> Tuple[Optional[str], int]:
    """
    预处理图片：下载、检测方向、旋转矫正。
    
    Args:
        image_url: 原始图片 URL
        
    Returns:
        (处理后的 base64 数据 URL 或 None, 旋转角度)
        如果处理失败，返回 (None, 0)，调用方应回退到使用原始 URL
    """
    # 检查是否启用预处理
    if not getattr(settings, 'ENABLE_IMAGE_ROTATION', True):
        logger.debug("图片旋转预处理已禁用")
        return None, 0
    
    try:
        # 下载图片
        img = load_image_from_url(image_url)
        if img is None:
            return None, 0
        
        # 检测并旋转
        corrected_img, angle = detect_and_rotate(img)
        
        # 转换为 base64
        base64_url = image_to_base64_url(corrected_img)
        
        return base64_url, angle
        
    except Exception as e:
        logger.error(f"图片预处理失败: {e}")
        return None, 0
