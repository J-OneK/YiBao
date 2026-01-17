import cv2
import numpy as np
from paddleocr import PaddleOCR

# 初始化 PaddleOCR (只需加载一次)
# lang='en' 针对英文单据，use_angle_cls=False 因为我们要手动旋转判断
ocr_engine = PaddleOCR(use_angle_cls=False, det_limit_side_len=2500, lang='ch')

def get_best_orientation(img_path):
    img = cv2.imread(img_path)
    h, w = img.shape[:2]
    
    # 为了速度，可以将图片缩小一点来做判断（可选，例如最长边缩放到 1000）
    # 但为了准确度，建议保持原图或适度缩放
    
    angles = [0, 90, 180, 270]
    best_angle = 0
    max_score = 0
    
    print(f"正在分析图片: {img_path} ...")

    for angle in angles:
        # 1. 旋转图片
        if angle == 0:
            rotated_img = img
        elif angle == 90:
            rotated_img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            rotated_img = cv2.rotate(img, cv2.ROTATE_180)
        elif angle == 270:
            rotated_img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # debug_path = f"debug_angle_{angle}.jpg"
        # cv2.imwrite(debug_path, rotated_img)

        # 2. 运行 OCR 检测 (只做检测和识别，取前几个结果即可判断)
        # 这里的关键是：如果方向不对，Paddle 根本检测不到多少有效的文本框
        try:
            result = ocr_engine.ocr(rotated_img, cls=False)
        except Exception:
            result = [[]]

        # 3. 计算“得分”
        # 评分规则：可以使用 (识别出的框数量) * (平均置信度)
        if result and result[0]:
            boxes = [line[0] for line in result[0]]
            scores = [line[1][1] for line in result[0]]
            
            # 核心逻辑：正确方向通常会有更多的文本框，且置信度更高
            # 简单粗暴点：直接用识别到的 文本框数量 * 平均置信度
            avg_score = sum(scores) / len(scores)
            total_score = len(boxes) * avg_score
        else:
            total_score = 0
            
        print(f"  -> 尝试旋转 {angle}°: 得分 {total_score:.2f} (检测到 {len(boxes) if result and result[0] else 0} 个框)")

        if total_score > max_score:
            max_score = total_score
            best_angle = angle

    return best_angle

# --- 使用 ---
correct_angle = get_best_orientation("/Users/1k/code/YiBao/jyk/test_pos/0_报关资料.pdf (1).png")
print(f"最终判定图片应该旋转: {correct_angle} 度")

# 如果需要，执行最终旋转并保存
if correct_angle != 0:
    original = cv2.imread("/Users/1k/code/YiBao/jyk/test_pos/0_报关资料.pdf (1).png")
    if correct_angle == 180:
        final = cv2.rotate(original, cv2.ROTATE_180)
        cv2.imwrite("/Users/1k/code/YiBao/jyk/PaddleOCR/180.png", final)
    elif correct_angle == 270:
        final = cv2.rotate(original, cv2.ROTATE_270)
        cv2.imwrite("/Users/1k/code/YiBao/jyk/PaddleOCR/270.png", final)
    elif correct_angle == 90:
        final = cv2.rotate(original, cv2.ROTATE_90)
        cv2.imwrite("/Users/1k/code/YiBao/jyk/PaddleOCR/90.png", final)