import cv2
import numpy as np
from paddleocr import PaddleOCR

def safe_run_ocr():
    img_path = '/Users/1k/code/YiBao/jyk/test_pos/0_报关资料.pdf (1).png'  # <--- 替换你的文件名

    print(f"1. 正在读取图片: {img_path}")
    # 使用 UNCHANGED 读取，保留透明通道
    img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)

    if img is None:
        print("❌ 错误：无法读取，路径不对或有中文路径。")
        return

    # --- 核心修复：处理透明背景 ---
    if len(img.shape) == 3 and img.shape[2] == 4:
        print("⚠️ 发现透明通道(Alpha)，正在填充白色背景...")
        # 分离 alpha 通道
        alpha_channel = img[:, :, 3]
        rgb_channels = img[:, :, :3]

        # 构造白底
        white_bg = np.ones_like(rgb_channels, dtype=np.uint8) * 255

        # 融合: alpha * 前景 + (1-alpha) * 背景
        alpha_factor = alpha_channel[:, :, np.newaxis] / 255.0
        img = (rgb_channels * alpha_factor + white_bg * (1 - alpha_factor)).astype(np.uint8)
        
        print("✅ 透明背景已修复为白色。")
    elif len(img.shape) == 2:
        print("⚠️ 图片是灰度图，转换为BGR...")
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    # --- 强制保存一张用于人眼检查 ---
    cv2.imwrite("debug_check.jpg", img)
    print("📸 已保存 'debug_check.jpg'，请务必打开它！看是不是黑底黑字？")

    # --- 开始手动旋转测试 ---
    # 初始化 OCR，注意这里不要加乱七八糟的参数，只要这几个
    ocr = PaddleOCR(use_angle_cls=False, lang='ch', det_limit_side_len=2500)

    for angle in [0, 90, 180, 270]:
        if angle == 0:
            rotated = img
        elif angle == 90:
            rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            rotated = cv2.rotate(img, cv2.ROTATE_180)
        elif angle == 270:
            rotated = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # 再次保存旋转过程图，确保万无一失
        cv2.imwrite(f"debug_angle_{angle}.jpg", rotated)

        # 识别
        result = ocr.ocr(rotated)
        box_count = len(result[0]) if result and result[0] else 0
        print(f"角度 {angle}°: 检测到 {box_count} 个框")

safe_run_ocr()