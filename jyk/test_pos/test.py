import json
import cv2
import numpy as np

def visualize_coordinates(image_path, json_path, output_path):
    # 1. 读取 JSON 数据
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 2. 读取原始图片
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: 无法找到或读取图片 {image_path}")
        return

    # 获取图片初始物理尺寸
    current_h, current_w = img.shape[:2]
    print(f"原始图片尺寸: 宽={current_w}, 高={current_h}")

    # 3. 获取 JSON 中定义的尺寸和角度
    target_info = None
    target_image_id = 12
    
    # ... (此处省略你原有的 operateImage 查找代码，保持不变) ...
    # 假设你已经找到了 target_info
    # 如果没找到 target_info，给默认值防止报错
    json_w = current_w 
    json_h = current_h
    angle = 0

    if 'operateImage' in data['content']:
        # ... (你的查找逻辑) ...
        # 模拟找到数据
        operate_data = data['content']['operateImage']
        for item in operate_data:
             if isinstance(item, list):
                for img_meta in item:
                    if isinstance(img_meta, dict) and img_meta.get('imageId') == target_image_id:
                        target_info = img_meta
                        break
             elif isinstance(item, dict):
                 if item.get('imageId') == target_image_id:
                    target_info = item
                    break
             if target_info: break

    if target_info:
        json_w = int(target_info.get('imageWidth', 0))
        json_h = int(target_info.get('imageHeight', 0))
        angle = int(target_info.get('angle', 0))
        print(f"JSON 定义坐标系: 宽={json_w}, 高={json_h}, 角度={angle}")

        # 4. 旋转逻辑 (保持你原有的逻辑不变)
        if (json_w == current_h and json_h == current_w):
            print(">>> 旋转修正...")
            if angle == 270:
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            elif angle == 90:
                img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif angle == 180:
                img = cv2.rotate(img, cv2.ROTATE_180)
            
            # 重要：旋转后，所谓的“原始宽”和“原始高”其实互换了
            # 为了计算比例，我们需要交换 json_w 和 json_h 的概念来匹配当前图片的方向
            # 或者更简单的方法：直接取旋转后的 img.shape
        
    # === 核心修改点：重新获取旋转后的图片尺寸 ===
    final_img_h, final_img_w = img.shape[:2]
    
    # === 核心修改点：计算缩放比例 ===
    # 用 (当前图片实际尺寸 / JSON定义的尺寸)
    # 如果 JSON 里是 1000x1000 (归一化)，这里 scale 就会自动变成 "反归一化系数"
    # 如果 JSON 里是绝对像素，scale 就会接近 1.0
    
    # 防止除以0
    scale_x = final_img_w / json_w if json_w > 0 else 1.0
    scale_y = final_img_h / json_h if json_h > 0 else 1.0
    
    print(f"缩放比例: X轴={scale_x:.4f}, Y轴={scale_y:.4f}")

    boxes = []

    def extract_boxes(item_list):
        for item in item_list:
            label = item.get('keyDesc', item.get('key', 'Unknown'))
            for source in item.get('sourceList', []):
                if source.get('imageId') == target_image_id:
                    bx = source.get('axisX')
                    by = source.get('axisY')
                    bw = source.get('width')
                    bh = source.get('height')
                    
                    if bx is not None:
                        # === 核心修改点：应用缩放 ===
                        # 无论是归一化数据还是绝对坐标，乘上比例总是对的
                        real_x = int(bx * scale_x)
                        real_y = int(by * scale_y)
                        real_w = int(bw * scale_x)
                        real_h = int(bh * scale_y)
                        
                        boxes.append((real_x, real_y, real_w, real_h, label))

    # 提取数据 (保持不变)
    if 'preDecHead' in data['content']:
        extract_boxes(data['content']['preDecHead'])
    if 'preDecList' in data['content']:
        for row in data['content']['preDecList']:
            extract_boxes(row)

    print(f"共绘制 {len(boxes)} 个框")

    # 绘制
    for (x, y, w, h, label) in boxes:
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
        # 加上文字能更清楚看出是不是标对了
        # cv2.putText(img, label[:5], (x, max(y - 5, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

    cv2.imwrite(output_path, img)
    print(f"保存至: {output_path}")

# 调用部分保持不变
image_file = '/Users/1k/code/YiBao/jyk/test_pos/11_668E87B90CE4ECB5415DE28C22458CA3C1DD.pdf.png'
json_file = '/Users/1k/code/YiBao/public/归档/1ZG331E30458071596_output.json'
result_file = '/Users/1k/code/YiBao/jyk/test_pos/not_corrected_3.jpg'

visualize_coordinates(image_file, json_file, result_file)