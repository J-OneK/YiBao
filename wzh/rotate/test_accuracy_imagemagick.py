import io
import re
import json
import requests
import numpy as np
import cv2
import pytesseract
from PIL import Image
from wand.image import Image as WandImage
from tqdm import tqdm
import os
import tempfile

# ================= 1. 基础工具函数 =================

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
        distances = {
            0: min(norm_angle, 360 - norm_angle),
            90: abs(norm_angle - 90),
            180: abs(norm_angle - 180),
            270: abs(norm_angle - 270)
        }
        return min(distances, key=distances.get)

def coarse_adjust_with_tesseract(img):
    """粗调：使用 Tesseract 解决 90/180/270 度问题"""
    try:
        osd = pytesseract.image_to_osd(img)
        match = re.search(r'Rotate:\s*(\d+)', osd)
        angle = int(match.group(1)) if match else 0
        
        # Tesseract 返回的是需要顺时针旋转的角度
        # 转换为图片本身被旋转的角度
        if angle == 90:
            detected_angle = 270
        elif angle == 270:
            detected_angle = 90
        elif angle == 180:
            detected_angle = 180
        else:
            detected_angle = 0
            
        return detected_angle
    except Exception as e:
        return 0

# ================= 2. ImageMagick 精调检测 =================

def fine_tune_with_imagemagick(pil_img):
    """
    使用 ImageMagick deskew 进行精调检测
    完全在内存中处理，避免临时文件权限问题
    """
    try:
        # 将 PIL 图片转为字节流
        img_byte_arr = io.BytesIO()
        pil_img.save(img_byte_arr, format='JPEG', quality=95)
        img_byte_arr.seek(0)
        
        # 使用 Wand 处理
        with WandImage(blob=img_byte_arr.read()) as img:
            # 设置图片格式
            img.format = 'jpeg'
            
            # 使用 deskew，阈值设置为 40%
            img.deskew(0.4)
            
            # 直接从内存获取矫正后的图片数据
            deskewed_blob = img.make_blob('jpeg')
            
            # 从 blob 重新加载为 PIL 图片
            deskewed_pil = Image.open(io.BytesIO(deskewed_blob))
            
            # 使用 OpenCV 检测矫正后的残余倾斜
            cv_img = cv2.cvtColor(np.array(deskewed_pil), cv2.COLOR_RGB2BGR)
            residual_angle = calculate_residual_skew(cv_img)
            
            # 返回检测到的角度（取负值因为已被矫正）
            detected_angle = -residual_angle
            
            return round(detected_angle, 2)
            
    except Exception as e:
        # 静默失败，返回0
        return 0

def calculate_residual_skew(cv_img):
    """
    计算矫正后残余的倾斜角度
    用于验证 ImageMagick deskew 的效果
    """
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

# ================= 3. 粗调准确率测试（同原脚本）=================

def test_coarse_accuracy(dataset_path, output_dir="./test_results", limit=None):
    """测试粗调准确率（使用 Tesseract）"""
    os.makedirs(output_dir, exist_ok=True)
    
    coarse_error_dir = os.path.join(output_dir, "coarse_errors")
    os.makedirs(coarse_error_dir, exist_ok=True)
    
    with open(dataset_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
    
    if limit is not None:
        dataset = dataset[:limit]
        print(f"⚠️ 测试模式：只测试前 {limit} 张图片")
    
    results = []
    correct_count = 0
    total_count = 0
    
    print("=" * 60)
    print("开始粗调准确率测试 (Tesseract)")
    print("=" * 60)
    
    for idx, item in enumerate(tqdm(dataset, desc="粗调测试进度")):
        url = item['imageUrl']
        true_angle = item['angle']
        true_category = angle_to_category(true_angle)
        
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
        
        try:
            detected_angle = coarse_adjust_with_tesseract(img)
            detected_category = angle_to_category(detected_angle)
            
            is_correct = bool(true_category == detected_category)
            
            if is_correct:
                correct_count += 1
            else:
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
                'is_correct': bool(is_correct),
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
    
    accuracy = (correct_count / total_count * 100) if total_count > 0 else 0
    
    result_summary = {
        'test_type': 'coarse_adjustment_tesseract',
        'total_images': len(dataset),
        'successfully_tested': total_count,
        'correct_predictions': correct_count,
        'accuracy': accuracy,
        'details': results
    }
    
    output_file = os.path.join(output_dir, 'coarse_accuracy_results_imagemagick.json')
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

# ================= 4. 精调准确率测试（ImageMagick）=================

def test_fine_accuracy_imagemagick(dataset_path, coarse_results_details, output_dir="./test_results"):
    """
    测试精调准确率（使用 ImageMagick deskew）
    """
    os.makedirs(output_dir, exist_ok=True)
    
    fine_error_dir = os.path.join(output_dir, "fine_errors_imagemagick")
    os.makedirs(fine_error_dir, exist_ok=True)
    
    # 只处理粗调测试过的图片
    # 从粗调结果中提取已测试的图片信息
    dataset = []
    for result in coarse_results_details:
        dataset.append({
            'imageUrl': result['imageUrl'],
            'angle': result['true_angle'],
            'sourceFile': result.get('sourceFile', '')
        })
    
    coarse_results_map = {}
    for result in coarse_results_details:
        coarse_results_map[result['imageUrl']] = result
    
    results = []
    correct_count = 0
    total_count = 0
    angle_errors = []
    
    print("\n" + "=" * 60)
    print("开始精调准确率测试 (ImageMagick deskew)")
    print(f"将测试 {len(dataset)} 张图片的精调能力（与粗调相同）")
    print("=" * 60)
    
    for idx, item in enumerate(tqdm(dataset, desc="精调测试进度(ImageMagick)")):
        url = item['imageUrl']
        true_angle = item['angle']
        
        coarse_result = coarse_results_map.get(url, {})
        coarse_is_correct = coarse_result.get('is_correct', False)
        detected_coarse_angle = coarse_result.get('detected_category', None)
        
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
        
        if coarse_is_correct and detected_coarse_angle is not None:
            rotation_angle = detected_coarse_angle
            rotation_source = 'coarse_detection'
        else:
            true_category = angle_to_category(true_angle)
            rotation_angle = true_category
            rotation_source = 'true_angle_category'
        
        try:
            # 旋转图片到基本正确的方向
            # rotation_angle表示图片被顺时针旋转的角度
            # 要摆正需要逆时针旋转相同角度
            # PIL的rotate(正数)是逆时针，所以直接用rotation_angle
            if rotation_angle != 0:
                img_rotated = img.rotate(rotation_angle, expand=True)  # 修复：改为正数
            else:
                img_rotated = img
            
            # 使用 ImageMagick deskew 进行精调检测
            detected_fine_angle = fine_tune_with_imagemagick(img_rotated)
            
            # 计算真实的精调角度
            true_fine_angle = true_angle - rotation_angle
            
            if true_fine_angle > 180:
                true_fine_angle = true_fine_angle - 360
            elif true_fine_angle < -180:
                true_fine_angle = true_fine_angle + 360
            
            # 计算误差
            error = abs(detected_fine_angle - true_fine_angle)
            angle_errors.append(error)
            
            # ⚠️ 误差在±1度以内认为正确
            is_correct = bool(error <= 1)
            
            if is_correct:
                correct_count += 1
            else:
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
                'is_correct': bool(is_correct),
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
    
    accuracy = (correct_count / total_count * 100) if total_count > 0 else 0
    mean_error = np.mean(angle_errors) if angle_errors else 0
    median_error = np.median(angle_errors) if angle_errors else 0
    
    coarse_correct_errors = []
    coarse_wrong_errors = []
    for result in results:
        if result['status'] == 'success':
            if result['coarse_correct']:
                coarse_correct_errors.append(result['error'])
            else:
                coarse_wrong_errors.append(result['error'])
    
    coarse_correct_accuracy = (sum(1 for e in coarse_correct_errors if e <= 1) / len(coarse_correct_errors) * 100) if coarse_correct_errors else 0
    coarse_wrong_accuracy = (sum(1 for e in coarse_wrong_errors if e <= 1) / len(coarse_wrong_errors) * 100) if coarse_wrong_errors else 0
    
    result_summary = {
        'test_type': 'fine_adjustment_imagemagick',
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
    
    output_file = os.path.join(output_dir, 'fine_accuracy_results_imagemagick.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_summary, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print("精调测试完成！(ImageMagick)")
    print(f"总图片数: {len(dataset)}")
    print(f"成功测试: {total_count}")
    print(f"正确预测 (±1度): {correct_count}")
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

# ================= 5. 主函数 =================

def main():
    dataset_path = r"c:\desktop\YiBao\wzh\rotate\rotation_dataset.json"
    output_dir = r"c:\desktop\YiBao\wzh\rotate\test_results_imagemagick"
    
    # ⚠️ 测试模式：只测试前30张图片
    test_limit = None  # 设置为 None 可测试全部图片
    
    print("=" * 60)
    print("使用 ImageMagick Deskew 进行精调测试")
    print("粗调：Tesseract OSD")
    print("精调：ImageMagick deskew")
    print("=" * 60)
    
    # 测试粗调准确率
    print("\n开始测试粗调准确率...")
    coarse_results = test_coarse_accuracy(dataset_path, output_dir, limit=test_limit)
    
    # 测试精调准确率（传入粗调的详细结果）
    print("\n开始测试精调准确率...")
    fine_results = test_fine_accuracy_imagemagick(dataset_path, coarse_results['details'], output_dir)
    
    # 生成总结报告
    summary = {
        'method': 'ImageMagick_deskew',
        'coarse_adjustment': {
            'method': 'Tesseract_OSD',
            'accuracy': coarse_results['accuracy'],
            'total': coarse_results['total_images'],
            'correct': coarse_results['correct_predictions']
        },
        'fine_adjustment': {
            'method': 'ImageMagick_deskew',
            'accuracy': fine_results['accuracy'],
            'total': fine_results['total_images'],
            'correct': fine_results['correct_predictions'],
            'mean_error': fine_results['mean_error'],
            'median_error': fine_results['median_error'],
            'breakdown': fine_results['breakdown']
        }
    }
    
    summary_file = os.path.join(output_dir, 'summary_imagemagick.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print("\n" + "=" * 60)
    print("全部测试完成！汇总报告：")
    print(f"粗调准确率 (Tesseract): {coarse_results['accuracy']:.2f}%")
    print(f"精调总体准确率 (ImageMagick): {fine_results['accuracy']:.2f}%")
    print(f"  - 粗调正确时的精调准确率: {fine_results['breakdown']['coarse_correct']['accuracy']:.2f}%")
    print(f"  - 粗调错误时的精调准确率: {fine_results['breakdown']['coarse_wrong']['accuracy']:.2f}%")
    print(f"精调平均误差: {fine_results['mean_error']:.2f}度")
    print("=" * 60)

if __name__ == "__main__":
    main()
