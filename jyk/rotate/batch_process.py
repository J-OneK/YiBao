import json
import io
import re
import math
import requests
import numpy as np
import cv2
import pytesseract
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy

# ================= 1. 核心算法 (源自 rotate.py) =================

def rotate_image_full(image, angle):
    """旋转图片任意角度，并自动扩大画布"""
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    M[0, 2] += (new_w / 2) - center[0]
    M[1, 2] += (new_h / 2) - center[1]
    
    if len(image.shape) == 3:
        fill_color = (255, 255, 255) 
    else:
        fill_color = 255 
    
    rotated = cv2.warpAffine(image, M, (new_w, new_h), borderValue=fill_color)
    return rotated

def load_image_from_url(url, retries=3):
    """加载图片并确保转为 RGB，带重试机制"""
    for i in range(retries):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            return img
        except Exception as e:
            if i == retries - 1:
                print(f"❌ 下载失败 [{url}]: {e}")
                return None

def coarse_adjust_with_tesseract(img):
    """粗调：解决 90/180/270 度问题"""
    try:
        osd = pytesseract.image_to_osd(img)
        match = re.search(r'Rotate:\s*(\d+)', osd)
        angle = int(match.group(1)) if match else 0
        conf_match = re.search(r'Orientation confidence:\s*([\d\.]+)', osd)
        orientation_conf = float(conf_match.group(1)) if conf_match else 0.0
        print(orientation_conf)
        # Tesseract 的 Rotate 通常指“为了摆正需要旋转的角度”
        # 这里为了计算总角度，我们记录它建议的旋转量
        
        if angle != 0 and orientation_conf > 1:
            # Pillow rotate 是逆时针，Tesseract 返回的是顺时针需要的角度
            # 所以 rotate(angle) 还是 rotate(-angle)?
            # 通常 osd 返回 90 意味着图片是顺时针歪了90度，需要逆时针转90度修复
            # 但用户脚本里写的是 img.rotate(-angle)，我们保持用户逻辑一致
            img = img.rotate(-angle, expand=True)
        if orientation_conf <= 1:
            return img, 0
        if angle == 90 or angle == 270:
            angle = 360 - angle    
        return img, angle
    except Exception as e:
        # Tesseract 失败时回退
        return img, 0

def calculate_fine_skew(cv_img):
    """计算微小倾斜角度"""
    try:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        angles = []
        for cnt in contours:
            if cv2.contourArea(cnt) < 500: continue
            rect = cv2.minAreaRect(cnt)
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
    except:
        return 0.0

def fine_tune_and_rotate_custom(pil_img):
    """精调逻辑"""
    cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    skew_angle = calculate_fine_skew(cv_img)
    
    final_h, final_w = cv_img.shape[:2] # 默认为当前宽高

    if abs(skew_angle) > 0.1:
        final_cv_img = rotate_image_full(cv_img, skew_angle)
        final_h, final_w = final_cv_img.shape[:2]
        # 转回 Pillow 只是为了统一接口，实际这里主要需要宽高和角度
        return final_w, final_h, round(skew_angle)
    else:
        return final_w, final_h, 0.0

# ================= 2. 批处理逻辑 =================

def get_angle_diff(angle1, angle2):
    """计算两个角度的最小差值 (考虑 360 度循环)"""
    diff = abs(angle1 - angle2) % 360
    return min(diff, 360 - diff)

def process_item(item):
    """处理单条数据"""
    url = item.get("imageUrl")
    gt_angle = item.get("angle", 0) # Ground Truth
    
    result_item = copy.deepcopy(item)
    result_item["status"] = "failed"
    result_item["detected_angle"] = 0
    result_item["angle_error"] = 0
    result_item["is_correct"] = False
    
    if not url:
        return result_item

    # 1. 下载
    img = load_image_from_url(url)
    if img is None:
        return result_item

    # 2. 粗调 (Tesseract)
    # Tesseract 返回的是它认为图片偏转的角度。
    # 用户脚本逻辑：img.rotate(-angle)。
    # 这意味着如果 Tesseract 说 90，图片被转了 -90 (顺时针90) 修正？
    # 通常 Tesseract OSD Rotate: 90 意味着“图片顺时针歪了90度，请逆时针转90修复”。
    # Pillow rotate(90) 是逆时针。用户代码是 rotate(-angle)，即顺时针转。
    # 这块逻辑可能需要根据实际 Tesseract 版本确认，这里严格遵循用户 rotate.py 的写法。
    img_coarse, angle_coarse = coarse_adjust_with_tesseract(img)

    # 3. 精调
    width, height, angle_fine = fine_tune_and_rotate_custom(img_coarse)

    # 4. 计算总检测角度
    # 注意：这里的“检测角度”定义为“图片原本相对于正向偏转了多少度”
    # 如果代码做的是“修正”，那么 Detected Angle = (angle_coarse + angle_fine)
    # 或者是修正的相反数，取决于数据集 angle 的定义。
    # 假设数据集 angle=90 意味着图片是横着的。
    total_detected_angle = (angle_coarse) % 360
    
    # 5. 更新结果
    result_item["detected_imageWidth"] = str(width)
    result_item["detected_imageHeight"] = str(height)
    result_item["detected_angle"] = total_detected_angle
    result_item["status"] = "success"

    # 6. 计算准确率 (允许误差 ±3 度)
    # 归一化 Ground Truth (有些可能是 359，有些是 -1)
    norm_gt = gt_angle % 360
    norm_dt = total_detected_angle % 360
    
    error = get_angle_diff(norm_gt, norm_dt)
    result_item["angle_error"] = round(error, 2)
    
    # 判定是否准确：误差小于 3 度，或者 (针对 90/180/270 的情况) 允许 Tesseract 误判但精调正确的特殊逻辑？
    # 这里使用严格误差 < 3 度作为判定标准
    if error < 3:
        result_item["is_correct"] = True
    else:
        result_item["is_correct"] = False

    print(f"✅ [{result_item['sourceFile']}] GT: {gt_angle} | Det: {total_detected_angle:.1f} | Err: {error:.1f}")
    return result_item

def main():
    input_file = "/Users/1k/code/YiBao/jyk/rotate/rotation_dataset.json"
    output_file = "/Users/1k/code/YiBao/jyk/rotate/rotation_result_OSD.json"
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ 未找到 rotation_dataset.json")
        return

    print(f"🚀 开始处理 {len(data)} 张图片...")
    
    results = []
    correct_count = 0
    total_error = 0
    processed_count = 0

    # 使用线程池并发处理，建议 max_workers 设为 5-10
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_item = {executor.submit(process_item, item): item for item in data}
        
        for future in as_completed(future_to_item):
            res = future.result()
            results.append(res)
            
            if res["status"] == "success":
                processed_count += 1
                total_error += res["angle_error"]
                if res["is_correct"]:
                    correct_count += 1

    # 统计信息
    accuracy = (correct_count / processed_count * 100) if processed_count > 0 else 0
    avg_error = (total_error / processed_count) if processed_count > 0 else 0

    print("\n" + "="*40)
    print(f"📊 处理统计:")
    print(f"   - 总数量: {len(data)}")
    print(f"   - 成功处理: {processed_count}")
    print(f"   - 准确数量 (误差<3°): {correct_count}")
    print(f"   - 准确率: {accuracy:.2f}%")
    print(f"   - 平均角度误差: {avg_error:.2f}°")
    print("="*40)

    # 保存结果
    # 替换原字段还是新增字段？用户说“生成和原json格式一样的检测json”
    # 这里生成包含原字段 + detected_字段 的 JSON，方便后续核对。
    # 如果严格需要“覆盖”，可以将 detected_width 赋值给 imageWidth。
    
    final_output = []
    for item in results:
        # 创建一个符合原格式的干净字典
        clean_item = {
            "sourceFile": item.get("sourceFile"),
            "imageUrl": item.get("imageUrl"),
            # 这里将检测结果写入原字段，原字段放入 gt_ 前缀备份
            "angle": item.get("detected_angle"), 
            "imageWidth": item.get("detected_imageWidth"),
            "imageHeight": item.get("detected_imageHeight"),
            
            # 额外保留的信息用于分析
            "gt_angle": item.get("angle"), 
            "angle_error": item.get("angle_error"),
            "is_correct": item.get("is_correct")
        }
        final_output.append(clean_item)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=4)
    
    print(f"💾 结果已保存至: {output_file}")

if __name__ == "__main__":
    main()