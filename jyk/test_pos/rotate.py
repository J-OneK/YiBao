import cv2
import numpy as np

def rotate_image(image, angle):
    """
    旋转图片任意角度 (angle 为正数是逆时针，负数是顺时针)
    并自动填充白色背景。
    """
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)

    # 1. 获取旋转矩阵
    # 参数：旋转中心，旋转角度，缩放比例(1.0表示不缩放)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)

    # 2. 执行仿射变换
    # borderValue=(255, 255, 255) 表示边缘填充白色，适合 OCR
    # 如果是灰度图，用 borderValue=(255)
    if len(image.shape) == 3:
        fill_color = (255, 255, 255) # 彩色图填白
    else:
        fill_color = 255 # 灰度图填白

    rotated = cv2.warpAffine(image, M, (w, h), borderValue=fill_color)
    
    return rotated

# --- 使用示例 ---
# 读取图片
img = cv2.imread('/Users/1k/code/YiBao/jyk/test_pos/11_668E87B90CE4ECB5415DE28C22458CA3C1DD.pdf.png')

# 逆时针旋转 2 度
result = rotate_image(img, 2)

# 保存或显示
cv2.imwrite('/Users/1k/code/YiBao/jyk/test_pos/corrected.jpg', result)