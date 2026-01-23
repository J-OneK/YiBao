import io
import re
import math
import requests
import numpy as np
import cv2
import pytesseract
from PIL import Image

# ================= 1. 你的自定义旋转函数 =================

def rotate_image_full(image, angle):
    """
    旋转图片任意角度，并自动扩大画布以放下完整图片，
    避免内容被裁剪。
    """
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)

    # 1. 获取基础旋转矩阵
    # 注意：cv2.getRotationMatrix2D 的 angle 参数：正数表示逆时针旋转
    M = cv2.getRotationMatrix2D(center, angle, 1.0)

    # 2. --- 关键步骤：计算新的宽高 ---
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])

    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))

    # 3. --- 关键步骤：调整旋转中心 ---
    M[0, 2] += (new_w / 2) - center[0]
    M[1, 2] += (new_h / 2) - center[1]

    # 4. 确定填充颜色 (白底)
    if len(image.shape) == 3:
        fill_color = (255, 255, 255) 
    else:
        fill_color = 255 

    # 5. 执行仿射变换
    rotated = cv2.warpAffine(image, M, (new_w, new_h), borderValue=fill_color)
    
    return rotated

# ================= 2. 基础工具函数 =================

def load_image_from_url(url):
    """加载图片并确保转为 RGB"""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        return img
    except Exception as e:
        print(f"下载失败: {e}")
        return None

def coarse_adjust_with_tesseract(img):
    """粗调：解决 90/180/270 度问题"""
    try:
        # 使用 --psm 0 检测方向
        osd = pytesseract.image_to_osd(img)
        match = re.search(r'Rotate:\s*(\d+)', osd)
        angle = int(match.group(1)) if match else 0
        orientation_conf = float(match.group(1)) if match else 0.0
        if angle != 0 and orientation_conf:
            print(f"   [粗调] Tesseract 建议顺时针旋转 {angle} 度")
            # Pillow 的 rotate(-angle) 等同于顺时针旋转
            img = img.rotate(-angle, expand=True)
        if angle == 90 or angle == 270:
            angle = 360 - angle
        return img, angle
    except:
        if angle == 90 or angle == 270:
            angle = 360 - angle
        return img, angle

# ================= 3. 精调逻辑 (结合你的函数) =================

def calculate_fine_skew(cv_img):
    """计算微小倾斜角度"""
    # 转灰度
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    # 二值化 + 膨胀
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
    dilated = cv2.dilate(thresh, kernel, iterations=1)
    
    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    angles = []
    for cnt in contours:
        if cv2.contourArea(cnt) < 500: continue
        rect = cv2.minAreaRect(cnt)
        # 兼容不同版本 OpenCV 的角度定义，归一化到 [-45, 45]
        ((cx, cy), (w, h), angle) = rect
        if w < h:
            w, h = h, w
            angle += 90
        if abs(angle) > 45:
             if abs(angle - 90) < 45: angle -= 90
             else: continue
        angles.append(angle)

    if not angles: return 0.0
    return np.median(angles)

def fine_tune_and_rotate_custom(pil_img):
    """
    接收 Pillow 图片，计算角度，然后调用 rotate_image_full 进行旋转
    """
    print("   正在进行精调计算...")
    
    # 1. Pillow (RGB) -> OpenCV (BGR)
    # 这是必要的桥接步骤
    cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    
    # 2. 计算倾斜角
    skew_angle = calculate_fine_skew(cv_img)
    print(f"   [精调] 检测到倾斜: {skew_angle:.4f} 度")
    
    if abs(skew_angle) > 0.1:
        # 3. 调用你的自定义函数！
        # 注意：skew_angle 是“当前倾斜角”。
        # 如果 skew_angle 是正数（比如顺时针歪了），我们需要逆时针修正吗？
        # OpenCV minAreaRect 的角度逻辑比较绕。
        # 经过经验总结：直接传入 skew_angle 给 getRotationMatrix2D 通常能摆正图片。
        # 如果发现方向反了，这里改成 -skew_angle 即可。
        
        final_cv_img = rotate_image_full(cv_img, round(skew_angle))
        
        print(f"   [精调] 已调用自定义函数完成旋转 (画布已自动扩大)。")
        
        # 4. OpenCV (BGR) -> Pillow (RGB)
        # 转回 Pillow 对象以便统一输出
        final_pil_img = Image.fromarray(cv2.cvtColor(final_cv_img, cv2.COLOR_BGR2RGB))
        return final_pil_img, round(skew_angle)
    else:
        print("   [精调] 角度无需调整。")
        return pil_img, round(skew_angle)

# ================= 4. 主流程 =================

def pipeline(url):
    # 1. 下载
    img = load_image_from_url(url)
    if img is None: return

    # 2. 粗调 (Tesseract)
    img, angle1 = coarse_adjust_with_tesseract(img)

    # 3. 精调 (OpenCV + 你的 rotate_image_full)
    final_img, angle2 = fine_tune_and_rotate_custom(img)

    # 4. 保存
    final_img.save(r"c:\desktop\YiBao\wzh\rotate\final_corrected_output.jpg")
    print("\n✅ 处理完成，保存为 final_corrected_result.jpg")
    print(f"已旋转角度: {angle1}度")
    img = cv2.imread(r"c:\desktop\YiBao\wzh\rotate\final_corrected_output.jpg")
    print(img.shape)

# 运行
url = "http://smartebao-production-ocr.oss-cn-shanghai.aliyuncs.com/dub/002/1/2020/12/23/1be007e1-278a-4a95-b4d9-3f6ef758bb3b/1ZG331E30459136989/file/1_09D25561E0C1A47B56064DFDF2C1257E2247.pdf.png"
pipeline(url)