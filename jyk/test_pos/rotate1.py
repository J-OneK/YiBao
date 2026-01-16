import cv2
import numpy as np
import math

def rotate_image_full(image, angle):
    """
    旋转图片任意角度，并自动扩大画布以放下完整图片，
    避免内容被裁剪。
    """
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)

    # 1. 获取基础旋转矩阵
    M = cv2.getRotationMatrix2D(center, angle, 1.0)

    # 2. --- 关键步骤：计算新的宽高 ---
    # 获取旋转矩阵中的 cos 和 sin 值 (绝对值)
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])

    # 计算新图像的 bounding box 宽高
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))

    # 3. --- 关键步骤：调整旋转中心 ---
    # 因为画布变大了，原点发生了变化，需要加上偏移量
    M[0, 2] += (new_w / 2) - center[0]
    M[1, 2] += (new_h / 2) - center[1]

    # 4. 确定填充颜色
    if len(image.shape) == 3:
        fill_color = (255, 255, 255) # 彩色图填白
    else:
        fill_color = 255 # 灰度图填白

    # 5. 执行仿射变换，传入新的宽高 (new_w, new_h)
    rotated = cv2.warpAffine(image, M, (new_w, new_h), borderValue=fill_color)
    
    return rotated

# --- 使用示例 ---
img_path = '/Users/1k/code/YiBao/jyk/test_pos/11_668E87B90CE4ECB5415DE28C22458CA3C1DD.pdf.png'
img = cv2.imread(img_path)

if img is None:
    print("图片读取失败，请检查路径")
else:
    print(f"原图尺寸: {img.shape}")

    # 旋转 90 度 (或任意角度，如 2 度, 45 度)
    result = rotate_image_full(img, 2)

    print(f"旋转后尺寸: {result.shape}") # 尺寸应该变了

    # 保存
    save_path = '/Users/1k/code/YiBao/jyk/test_pos/corrected_full_2.jpg'
    cv2.imwrite(save_path, result)
    print(f"已保存到: {save_path}")