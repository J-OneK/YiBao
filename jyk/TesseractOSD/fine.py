import cv2
import numpy as np
import math

def calculate_fine_skew(image):
    """
    计算图片的微小倾斜角度 (基于 OpenCV 轮廓分析)
    返回: 需要旋转的角度 (float)，例如 1.5 或 -2.0
    """
    # 1. 预处理：转灰度 -> 二值化 (黑底白字)
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
        
    # 反转二值化：文字变白，背景变黑
    # 阈值设为 0 + OTSU，自动寻找最佳阈值
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    # 2. 核心步骤：膨胀 (Dilation)
    # 使用扁长的核 (width=30, height=1)，把同一行的文字融合成一条线
    # 针对你的表格单据，这步非常有效，横线和文字行都会变成很好的特征
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
    dilated = cv2.dilate(thresh, kernel, iterations=1)

    # (调试用) 你可以保存这张图看看，全是白色的横条
    # cv2.imwrite("debug_dilated.jpg", dilated)

    # 3. 寻找轮廓
    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    
    angles = []
    for cnt in contours:
        # 过滤噪点：太小的轮廓不要
        if cv2.contourArea(cnt) < 500:
            continue
            
        # 4. 最小外接矩形
        # rect 包含 ((center_x, center_y), (width, height), angle)
        rect = cv2.minAreaRect(cnt)
        ((cx, cy), (w, h), angle) = rect
        
        # minAreaRect 的角度定义比较复杂，OpenCV 不同版本有差异
        # 下面的逻辑将角度统一映射到 [-45, 45] 之间，表示相对于水平线的偏角
        
        # 如果矩形宽度 < 高度，说明 minAreaRect 算的是竖直方向的角度，需要修正
        if w < h:
            w, h = h, w
            angle += 90

        # 现在角度应该接近 0 度（水平）。如果 > 45 或 < -45，说明可能检测到了竖线
        # 我们只关心水平文本行的倾斜
        if abs(angle) > 45:
             # 有些版本的 OpenCV angle 返回 90 度表示水平，这里做个兜底
             if abs(angle - 90) < 45:
                 angle -= 90
             else:
                 continue # 忽略竖线干扰

        angles.append(angle)

    if not angles:
        return 0.0

    # 5. 投票：取中位数 (Median)
    # 中位数能完美过滤掉个别歪得离谱的 LOGO 或 签名
    final_angle = np.median(angles)
    
    # 限制最大矫正角度（防止误操作），一般精调不超过 10 度
    # 如果算出 30 度，那可能是粗调没做好，或者图片内容本身就是歪的艺术字
    if abs(final_angle) > 20:
        print(f"  [精调] 检测角度 {final_angle:.2f} 过大，可能是误判，放弃精调。")
        return 0.0

    return final_angle

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
# ================= 整合你的流程 =================

def full_pipeline(img_path):
    import cv2
    
    # 1. 读取
    img = cv2.imread(img_path)
    
    # --- 阶段一：Tesseract 粗调 (你的现有逻辑) ---
    # 假设你已经跑完了之前的逻辑，得到了一个大概正向的图片
    # coarse_corrected_img = smart_orientation_correction(img) 
    # 这里为了演示，假设 img 已经是经过 Tesseract 0/90/180/270 矫正后的图
    current_img = img 
    
    # --- 阶段二：OpenCV 精调 ---
    print("正在进行精细角度检测...")
    skew_angle = calculate_fine_skew(current_img)
    
    print(f"检测到微小倾斜: {skew_angle:.4f} 度")
    
    if abs(skew_angle) > 0.1:
        final_img = rotate_image_full(current_img, skew_angle)
        print(f"已执行旋转矫正。")
    else:
        final_img = current_img
        print("角度很正，无需旋转。")
        
    cv2.imwrite("fine_result.jpg", final_img)

# 测试
full_pipeline("/Users/1k/code/YiBao/jyk/test_pos/11_668E87B90CE4ECB5415DE28C22458CA3C1DD.pdf.png")