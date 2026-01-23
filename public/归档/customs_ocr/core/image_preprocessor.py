"""
图片预处理模块 - 使用 TesseractOSD 进行图片方向检测与旋转矫正
增加 OpenCV 精调功能，处理小角度倾斜并自动扩展画布
集成阿里云OSS上传功能
"""
import logging
import base64
import io
import re
import os
import tempfile
from typing import Tuple, Optional

import cv2
import numpy as np
import requests
import pytesseract
from PIL import Image

from config import settings
from .AliyunOSSUploader import AliyunOSSUploader

logger = logging.getLogger(__name__)

# OSS上传器实例（延迟初始化）
_OSS_UPLOADER = None



def _get_oss_uploader() -> Optional[AliyunOSSUploader]:
    """
    获取OSS上传器实例（单例模式）
    
    Returns:
        AliyunOSSUploader实例，失败返回None
    """
    global _OSS_UPLOADER
    if _OSS_UPLOADER is None:
        try:
            # 尝试从配置文件读取
            try:
                from config.oss_config import OSS_CONFIG
            except ImportError:
                # 兼容性尝试：如果直接运行或路径设置不同，尝试从上级导入
                try:
                    from ..config.oss_config import OSS_CONFIG
                except ImportError:
                    # 再试一下旧的路径（以防万一）
                    from .oss_config import OSS_CONFIG
            _OSS_UPLOADER = AliyunOSSUploader(
                access_key_id=OSS_CONFIG["access_key_id"],
                access_key_secret=OSS_CONFIG["access_key_secret"],
                bucket_name=OSS_CONFIG["bucket_name"],
                public_endpoint=OSS_CONFIG["public_endpoint"]
            )
            logger.info("OSS上传器初始化成功")
        except ImportError:
            logger.warning("未找到oss_config.py配置文件，OSS上传功能将禁用")
            return None
        except Exception as e:
            logger.error(f"OSS上传器初始化失败: {e}")
            return None
    return _OSS_UPLOADER


# ================= 精调旋转相关函数 =================

def rotate_image_full(image: np.ndarray, angle: float) -> np.ndarray:
    """
    旋转图片任意角度，并自动扩大画布以放下完整图片，避免内容被裁剪。
    
    Args:
        image: OpenCV 图片 (numpy array)
        angle: 旋转角度（正数表示逆时针旋转）
        
    Returns:
        旋转后的图片
    """
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)

    # 获取基础旋转矩阵
    M = cv2.getRotationMatrix2D(center, angle, 1.0)

    # 计算新的宽高
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))

    # 调整旋转中心
    M[0, 2] += (new_w / 2) - center[0]
    M[1, 2] += (new_h / 2) - center[1]

    # 确定填充颜色 (白底)
    if len(image.shape) == 3:
        fill_color = (255, 255, 255)
    else:
        fill_color = 255

    # 执行仿射变换
    rotated = cv2.warpAffine(image, M, (new_w, new_h), borderValue=fill_color)
    return rotated


def calculate_fine_skew(cv_img: np.ndarray) -> float:
    """
    计算图片的微小倾斜角度。
    
    Args:
        cv_img: OpenCV 格式的图片 (BGR)
        
    Returns:
        倾斜角度（度）
    """
    # 转灰度
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    # 二值化 + 膨胀
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
    dilated = cv2.dilate(thresh, kernel, iterations=1)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    angles = []
    for cnt in contours:
        if cv2.contourArea(cnt) < 500:
            continue
        rect = cv2.minAreaRect(cnt)
        ((cx, cy), (w, h), angle) = rect
        if w < h:
            w, h = h, w
            angle += 90
        if abs(angle) > 45:
            if abs(angle - 90) < 45:
                angle -= 90
            else:
                continue
        angles.append(angle)

    if not angles:
        return 0.0
    return float(np.median(angles))


def fine_tune_rotate(pil_img: Image.Image) -> Tuple[Image.Image, int]:
    """
    对图片进行精调旋转，处理小角度倾斜。
    
    Args:
        pil_img: Pillow Image 对象
        
    Returns:
        (精调后的图片, 旋转角度)
    """
    logger.debug("正在进行精调计算...")
    
    # Pillow (RGB) -> OpenCV (BGR)
    cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    
    # 计算倾斜角
    skew_angle = calculate_fine_skew(cv_img)
    logger.debug(f"[精调] 检测到倾斜: {skew_angle:.4f} 度")
    
    if abs(skew_angle) > 0.1:
        # 调用画布扩展旋转函数
        final_cv_img = rotate_image_full(cv_img, round(skew_angle))
        logger.debug(f"[精调] 已完成旋转 {round(skew_angle)} 度 (画布已自动扩大)")
        
        # OpenCV (BGR) -> Pillow (RGB)
        final_pil_img = Image.fromarray(cv2.cvtColor(final_cv_img, cv2.COLOR_BGR2RGB))
        return final_pil_img, round(skew_angle)
    else:
        logger.debug("[精调] 角度无需调整")
        return pil_img, 0


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
    先进行粗调（90/180/270度），再进行精调（小角度倾斜矫正）。
    
    Args:
        img: Pillow Image 对象
        
    Returns:
        (校正后的图片, 总旋转角度)
    """
    coarse_angle = 0
    fine_angle = 0
    corrected_img = img
    
    # ================= 粗调：Tesseract OSD =================
    try:
        logger.debug("正在进行 OSD 方向检测（粗调）...")
        osd_result_text = pytesseract.image_to_osd(img)
        
        logger.debug(f"Tesseract OSD 输出: {osd_result_text.strip()}")

        # 解析输出结果
        rotate_match = re.search(r'Rotate:\s*(\d+)', osd_result_text)
        rotate_angle = int(rotate_match.group(1)) if rotate_match else 0
        
        conf_match = re.search(r'Orientation confidence:\s*([\d\.]+)', osd_result_text)
        orientation_conf = float(conf_match.group(1)) if conf_match else 0.0
        
        script_match = re.search(r'Script:\s*([a-zA-Z]+)', osd_result_text)
        script_name = script_match.group(1) if script_match else "Unknown"
        
        script_conf_match = re.search(r'Script confidence:\s*([\d\.]+)', osd_result_text)
        script_conf = float(script_conf_match.group(1)) if script_conf_match else 0.0

        logger.debug(f"检测结果 -> 角度: {rotate_angle}°, 语言: {script_name}, 方向置信度: {orientation_conf}, 语言置信度: {script_conf}")

        # 执行粗调旋转
        if rotate_angle > 0 and orientation_conf > 0.5:
            # Pillow 的 rotate 方法默认是逆时针旋转
            # Tesseract 告诉我们需要顺时针旋转，所以传入负值
            corrected_img = img.rotate(-rotate_angle, expand=True)
            coarse_angle = rotate_angle
            logger.info(f"[粗调] 图片已顺时针旋转 {rotate_angle} 度")
        else:
            logger.debug("[粗调] 图片方向正确或方向置信度过低，跳过粗调")

    except pytesseract.TesseractError as e:
        logger.warning(f"Tesseract OSD 检测失败: {e}，跳过粗调")
    except Exception as e:
        logger.warning(f"粗调方向检测发生未知错误: {e}，跳过粗调")
    
    # ================= 精调：OpenCV 小角度矫正 =================
    try:
        corrected_img, fine_angle = fine_tune_rotate(corrected_img)
        if fine_angle != 0:
            logger.info(f"[精调] 图片已旋转 {fine_angle} 度")
    except Exception as e:
        logger.warning(f"精调旋转发生错误: {e}，跳过精调")
        fine_angle = 0
    
    total_angle = coarse_angle + fine_angle
    if total_angle != 0:
        logger.info(f"总旋转角度: {total_angle} 度 (粗调 {coarse_angle}° + 精调 {fine_angle}°)")
    logger.info(f"当前图片大小:{corrected_img.size}")
    return corrected_img, total_angle


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


def preprocess_image(image_url: str) -> Tuple[Optional[str], int, int, int]:
    """
    预处理图片：下载、检测方向、旋转矫正、上传到OSS。
    
    Args:
        image_url: 原始图片 URL
        
    Returns:
        (处理后的OSS URL或base64 URL或None, 旋转角度, 宽度, 高度)
        如果处理失败，返回 (None, 0, 0, 0)，调用方应回退到使用原始 URL
    """
    # 检查是否启用预处理
    if not getattr(settings, 'ENABLE_IMAGE_ROTATION', True):
        logger.debug("图片旋转预处理已禁用")
        return None, 0, 0, 0
    
    temp_file_path = None
    try:
        # 下载图片
        img = load_image_from_url(image_url)
        if img is None:
            return None, 0, 0, 0
        
        # 检测并旋转
        corrected_img, angle = detect_and_rotate(img)
        width, height = corrected_img.size

        # 尝试上传到OSS
        oss_uploader = _get_oss_uploader()
        if oss_uploader is not None:
            try:
                # 保存到临时文件
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                    temp_file_path = temp_file.name
                    # 转换为RGB模式（JPEG不支持RGBA）
                    if corrected_img.mode == 'RGBA':
                        corrected_img = corrected_img.convert('RGB')
                    corrected_img.save(temp_file_path, format='JPEG', quality=95)
                
                # 从原始URL提取文件名
                original_filename = os.path.basename(image_url.split('?')[0])  # 去除URL参数
                if not original_filename or '.' not in original_filename:
                    original_filename = 'image.jpg'  # 默认文件名
                
                # 上传到OSS（使用MD5文件名，但保留原文件名用于下载）
                oss_url = oss_uploader.upload_file(
                    temp_file_path,
                    use_md5_filename=True,
                    preserve_original_name=True,  # 保留原文件名，方便下载时识别
                    original_filename=original_filename  # 传递从URL提取的原始文件名
                )
                
                if oss_url:
                    logger.info(f"图片已上传到OSS: {oss_url}")
                    return oss_url, angle, width, height
                else:
                    logger.warning("OSS上传失败，降级使用base64")
            except Exception as e:
                logger.error(f"OSS上传出错: {e}，降级使用base64")
            finally:
                # 清理临时文件
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                    except:
                        pass
        
        # 如果OSS上传失败或未配置，降级使用base64
        base64_url = image_to_base64_url(corrected_img)
        logger.debug("使用base64格式返回图片")
        return base64_url, angle, width, height 
        
    except Exception as e:
        logger.error(f"图片预处理失败: {e}")
        return None, 0, 0, 0
    finally:
        # 确保临时文件被清理
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
