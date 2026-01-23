import io
import re
import json
import requests
import numpy as np
import cv2
import pytesseract
from PIL import Image
from tqdm import tqdm
import os

# ================= 1. 导入原有的旋转检测函数 =================

def rotate_image_full(image, angle):
    """
    旋转图片任意角度，并自动扩大画布以放下完整图片，
    避免内容被裁剪。
    """
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
        
        # 注意：Tesseract 返回的是需要顺时针旋转的角度
        # 我们这里返回检测到的旋转角度（图片本身被旋转了多少度）
        if angle == 90:
            detected_angle = 270  # 图片本身逆时针旋转了270度
        elif angle == 270:
            detected_angle = 90   # 图片本身逆时针旋转了90度
        elif angle == 180:
            detected_angle = 180
        else:
            detected_angle = 0
            
        return detected_angle
    except Exception as e:
        return 0

def calculate_fine_skew(cv_img):
    """计算微小倾斜角度"""
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
    
    # OpenCV minAreaRect的angle:
    # 负数 = 逆时针倾斜
    # 正数 = 顺时针倾斜（经过我们的转换后）
    # 
    # 我们需要返回"图片被旋转的角度"
    # 如果检测到angle=-5（逆时针倾斜5度）
    # 说明图片是被顺时针旋转5度造成的
    # 所以返回 -(-5) = 5
    median_angle = np.median(angles)
    return -median_angle  # 取反！

def fine_tune_detect(pil_img):
    """
    精调检测：返回检测到的微小倾斜角度
    """
    cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    skew_angle = calculate_fine_skew(cv_img)
    return round(skew_angle)

# ================= 2. 准确率测试函数 =================

def normalize_angle(angle):
    """将角度标准化到 [0, 360) 范围"""
    return angle % 360

def angle_to_category(angle):
    """
    将角度分类：
    0-5度 或 355-360度 -> 0
    85-95度 -> 90
    175-185度 -> 180
    265-275度 -> 270
    """
    norm_angle = normalize_angle(angle)
    
    if (norm_angle >= 0 and norm_angle <= 5) or (norm_angle >= 355 and norm_angle < 360):
        return 0
    elif norm_angle >= 85 and norm_angle <= 95:
        return 90
    elif norm_angle >= 175 and norm_angle <= 185:
        return 180
    elif norm_angle >= 265 and norm_angle <= 275:
        return 270
    else:
        # 对于不在标准范围内的角度，返回最接近的标准角度
        # 这样在精调时才能正确旋转
        distances = {
            0: min(norm_angle, 360 - norm_angle),
            90: abs(norm_angle - 90),
            180: abs(norm_angle - 180),
            270: abs(norm_angle - 270)
        }
        return min(distances, key=distances.get)

def test_coarse_accuracy(dataset_path, output_dir="./test_results", limit=None):
    """
    测试粗调准确率
    
    粗调定义：能否正确检测出 90/180/270 度的大角度旋转
    - 真实角度在 85-95 度范围 -> 应检测为 90 度
    - 真实角度在 175-185 度范围 -> 应检测为 180 度
    - 真实角度在 265-275 度范围 -> 应检测为 270 度
    - 真实角度在 0-5 或 355-360 度范围 -> 应检测为 0 度
    
    注意：90度和270度必须严格区分，不能互认
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建错误图片保存目录
    coarse_error_dir = os.path.join(output_dir, "coarse_errors")
    os.makedirs(coarse_error_dir, exist_ok=True)
    
    # 加载数据集
    with open(dataset_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
    
    # 如果设置了limit，只测试前N张
    if limit is not None:
        dataset = dataset[:limit]
        print(f"⚠️ 测试模式：只测试前 {limit} 张图片")
    
    results = []
    correct_count = 0
    total_count = 0
    
    print("=" * 60)
    print("开始粗调准确率测试")
    print("=" * 60)
    
    for idx, item in enumerate(tqdm(dataset, desc="粗调测试进度")):
        url = item['imageUrl']
        true_angle = item['angle']
        
        # 将真实角度分类
        true_category = angle_to_category(true_angle)
        
        # 下载图片
        img = load_image_from_url(url)
        if img is None:
            results.append({
                'index': idx,
                'sourceFile': item['sourceFile'],
                'imageUrl': url,
                'true_angle': true_angle,
                'true_category': true_category,
                'detected_angle': None,
                'status': 'download_failed'
            })
            continue
        
        # 粗调检测
        try:
            detected_angle = coarse_adjust_with_tesseract(img)
            detected_category = angle_to_category(detected_angle)
            
            # 判断是否正确：必须严格匹配
            is_correct = (true_category == detected_category)
            
            if is_correct:
                correct_count += 1
            else:
                # 粗调错误：保存图片
                save_filename = f"{idx:04d}_true{true_angle}_detected{detected_angle}.jpg"
                save_path = os.path.join(coarse_error_dir, save_filename)
                img.save(save_path)
            
            total_count += 1
            
            results.append({
                'index': idx,
                'sourceFile': item['sourceFile'],
                'imageUrl': url,
                'true_angle': true_angle,
                'true_category': true_category,
                'detected_angle': detected_angle,
                'detected_category': detected_category,
                'is_correct': is_correct,
                'status': 'success'
            })
            
        except Exception as e:
            results.append({
                'index': idx,
                'sourceFile': item['sourceFile'],
                'imageUrl': url,
                'true_angle': true_angle,
                'true_category': true_category,
                'detected_angle': None,
                'status': f'error: {str(e)}'
            })
    
    # 计算准确率
    accuracy = (correct_count / total_count * 100) if total_count > 0 else 0
    
    # 保存结果
    result_summary = {
        'test_type': 'coarse_adjustment',
        'total_images': len(dataset),
        'successfully_tested': total_count,
        'correct_predictions': correct_count,
        'accuracy': accuracy,
        'details': results
    }
    
    output_file = os.path.join(output_dir, 'coarse_accuracy_results.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_summary, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print("粗调测试完成！")
    print(f"总图片数: {len(dataset)}")
    print(f"成功测试: {total_count}")
    print(f"正确预测: {correct_count}")
    print(f"准确率: {accuracy:.2f}%")
    print(f"结果已保存到: {output_file}")
    print("=" * 60)
    
    return result_summary

def test_fine_accuracy(dataset_path, coarse_results_details, output_dir="./test_results"):
    """
    测试精调准确率
    
    精调定义：在粗调之后，能否继续检测出微小倾斜角度
    
    策略：
    1. 如果粗调正确：使用粗调检测的角度旋转图片，然后测精调
    2. 如果粗调错误：使用真实角度的归一化分类值旋转图片，然后测精调
       - 例如：真实92° -> 归一化为90° -> 旋转90° -> 剩余2°需要精调
       - 而不是直接用92°，那样就没有精调测试的意义了
    
    这样可以测试算法在图片基本摆正后的微小角度检测能力
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建精调错误图片保存目录
    fine_error_dir = os.path.join(output_dir, "fine_errors")
    os.makedirs(fine_error_dir, exist_ok=True)
    
    # 加载数据集
    with open(dataset_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
    
    # 创建粗调结果索引（通过imageUrl快速查找）
    coarse_results_map = {}
    for result in coarse_results_details:
        coarse_results_map[result['imageUrl']] = result
    
    results = []
    correct_count = 0
    total_count = 0
    angle_errors = []
    
    print("\n" + "=" * 60)
    print("开始精调准确率测试")
    print(f"将测试所有 {len(dataset)} 张图片的精调能力")
    print("=" * 60)
    
    for idx, item in enumerate(tqdm(dataset, desc="精调测试进度")):
        url = item['imageUrl']
        true_angle = item['angle']
        
        # 获取对应的粗调结果
        coarse_result = coarse_results_map.get(url, {})
        coarse_is_correct = coarse_result.get('is_correct', False)
        detected_coarse_angle = coarse_result.get('detected_category', None)
        
        # 下载图片
        img = load_image_from_url(url)
        if img is None:
            results.append({
                'index': idx,
                'sourceFile': item['sourceFile'],
                'imageUrl': url,
                'true_angle': true_angle,
                'coarse_correct': coarse_is_correct,
                'rotation_angle_used': None,
                'detected_fine_angle': None,
                'status': 'download_failed'
            })
            continue
        
        # 决定使用哪个角度进行旋转
        if coarse_is_correct and detected_coarse_angle is not None:
            # 粗调正确：使用检测到的粗调角度
            rotation_angle = detected_coarse_angle
            rotation_source = 'coarse_detection'
        else:
            # 粗调错误或无结果：使用真实角度的归一化分类值
            # 例如：真实角度92° -> 归一化为90°，这样旋转后还有2°的偏差需要精调检测
            # 而不是直接用92°，那样就没有精调的意义了
            true_category = angle_to_category(true_angle)
            rotation_angle = true_category
            rotation_source = 'true_angle_category'
        
        try:
            # 旋转图片到基本正确的方向
            # rotation_angle表示图片被顺时针旋转的角度
            # 要摆正需要逆时针旋转相同角度
            # PIL的rotate(正数)是逆时针，所以直接用rotation_angle
            if rotation_angle != 0:
                img_rotated = img.rotate(rotation_angle, expand=True)  # 修复：正数=逆时针
            else:
                img_rotated = img
            
            # 精调检测
            detected_fine_angle = fine_tune_detect(img_rotated)
            
            # 计算真实的精调角度（真实角度 - 粗调分类角度）
            true_fine_angle = true_angle - rotation_angle
            
            # 标准化到 [-5, 5] 范围
            # 处理跨越0度的情况
            if true_fine_angle > 180:
                true_fine_angle = true_fine_angle - 360
            elif true_fine_angle < -180:
                true_fine_angle = true_fine_angle + 360
            
            # 计算误差
            error = abs(detected_fine_angle - true_fine_angle)
            angle_errors.append(error)
            
            # ⚠️ 误差在±1度以内认为正确（阈值从2度改为1度）
            is_correct = error <= 1
            
            if is_correct:
                correct_count += 1
            else:
                # 精调错误：保存旋转后的图片
                save_filename = f"{idx:04d}_true{true_angle}_rot{rotation_angle}_fine{true_fine_angle:.1f}_detected{detected_fine_angle}.jpg"
                save_path = os.path.join(fine_error_dir, save_filename)
                img_rotated.save(save_path)
            
            total_count += 1
            
            results.append({
                'index': idx,
                'sourceFile': item['sourceFile'],
                'imageUrl': url,
                'true_angle': true_angle,
                'true_category': angle_to_category(true_angle),
                'coarse_correct': coarse_is_correct,
                'rotation_angle_used': rotation_angle,
                'rotation_source': rotation_source,
                'true_fine_angle': true_fine_angle,
                'detected_fine_angle': detected_fine_angle,
                'error': error,
                'is_correct': is_correct,
                'status': 'success'
            })
            
        except Exception as e:
            results.append({
                'index': idx,
                'sourceFile': item['sourceFile'],
                'imageUrl': url,
                'true_angle': true_angle,
                'coarse_correct': coarse_is_correct,
                'rotation_angle_used': rotation_angle,
                'rotation_source': rotation_source,
                'detected_fine_angle': None,
                'status': f'error: {str(e)}'
            })
    
    # 计算准确率和平均误差
    accuracy = (correct_count / total_count * 100) if total_count > 0 else 0
    mean_error = np.mean(angle_errors) if angle_errors else 0
    median_error = np.median(angle_errors) if angle_errors else 0
    
    # 按照粗调正确/错误分组统计
    coarse_correct_errors = []
    coarse_wrong_errors = []
    for result in results:
        if result['status'] == 'success':
            if result['coarse_correct']:
                coarse_correct_errors.append(result['error'])
            else:
                coarse_wrong_errors.append(result['error'])
    
    coarse_correct_accuracy = (sum(1 for e in coarse_correct_errors if e <= 2) / len(coarse_correct_errors) * 100) if coarse_correct_errors else 0
    coarse_wrong_accuracy = (sum(1 for e in coarse_wrong_errors if e <= 2) / len(coarse_wrong_errors) * 100) if coarse_wrong_errors else 0
    
    # 保存结果
    result_summary = {
        'test_type': 'fine_adjustment',
        'total_images': len(dataset),
        'successfully_tested': total_count,
        'correct_predictions': correct_count,
        'accuracy': accuracy,
        'mean_error': float(mean_error),
        'median_error': float(median_error),
        'breakdown': {
            'coarse_correct': {
                'count': len(coarse_correct_errors),
                'accuracy': coarse_correct_accuracy,
                'mean_error': float(np.mean(coarse_correct_errors)) if coarse_correct_errors else 0
            },
            'coarse_wrong': {
                'count': len(coarse_wrong_errors),
                'accuracy': coarse_wrong_accuracy,
                'mean_error': float(np.mean(coarse_wrong_errors)) if coarse_wrong_errors else 0
            }
        },
        'details': results
    }
    
    output_file = os.path.join(output_dir, 'fine_accuracy_results.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_summary, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print("精调测试完成！")
    print(f"总图片数: {len(dataset)}")
    print(f"成功测试: {total_count}")
    print(f"正确预测 (±2度): {correct_count}")
    print(f"总体准确率: {accuracy:.2f}%")
    print(f"平均误差: {mean_error:.2f}度")
    print(f"中位数误差: {median_error:.2f}度")
    print("\n分组统计：")
    print(f"  粗调正确的图片 ({len(coarse_correct_errors)}张):")
    print(f"    精调准确率: {coarse_correct_accuracy:.2f}%")
    print(f"    平均误差: {np.mean(coarse_correct_errors) if coarse_correct_errors else 0:.2f}度")
    print(f"  粗调错误的图片 ({len(coarse_wrong_errors)}张):")
    print(f"    精调准确率: {coarse_wrong_accuracy:.2f}%")
    print(f"    平均误差: {np.mean(coarse_wrong_errors) if coarse_wrong_errors else 0:.2f}度")
    print(f"结果已保存到: {output_file}")
    print("=" * 60)
    
    return result_summary

# ================= 3. 主函数 =================

def main():
    dataset_path = r"c:\desktop\YiBao\wzh\rotate\rotation_dataset.json"
    output_dir = r"c:\desktop\YiBao\wzh\rotate\test_results"
    
    # ⚠️ 测试模式：只测试前30张图片
    test_limit = None  # 设置为 None 可测试全部图片
    
    # 测试粗调准确率
    print("开始测试粗调准确率...")
    coarse_results = test_coarse_accuracy(dataset_path, output_dir, limit=test_limit)
    
    # 测试精调准确率（传入粗调的详细结果）
    print("\n开始测试精调准确率...")
    fine_results = test_fine_accuracy(dataset_path, coarse_results['details'], output_dir)
    
    # 生成总结报告
    summary = {
        'coarse_adjustment': {
            'accuracy': coarse_results['accuracy'],
            'total': coarse_results['total_images'],
            'correct': coarse_results['correct_predictions']
        },
        'fine_adjustment': {
            'accuracy': fine_results['accuracy'],
            'total': fine_results['total_images'],
            'correct': fine_results['correct_predictions'],
            'mean_error': fine_results['mean_error'],
            'median_error': fine_results['median_error'],
            'breakdown': fine_results['breakdown']
        }
    }
    
    summary_file = os.path.join(output_dir, 'summary.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print("全部测试完成！汇总报告：")
    print(f"粗调准确率: {coarse_results['accuracy']:.2f}%")
    print(f"精调总体准确率: {fine_results['accuracy']:.2f}%")
    print(f"  - 粗调正确时的精调准确率: {fine_results['breakdown']['coarse_correct']['accuracy']:.2f}%")
    print(f"  - 粗调错误时的精调准确率: {fine_results['breakdown']['coarse_wrong']['accuracy']:.2f}%")
    print(f"精调平均误差: {fine_results['mean_error']:.2f}度")
    print("=" * 60)

if __name__ == "__main__":
    main()
