import json
import cv2
import numpy as np
import urllib.request
import os

def visualize_all_coordinates(json_path):
    # 1. 读取 JSON 数据
    if not os.path.exists(json_path):
        print(f"Error: 找不到指定的 JSON 文件 -> {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 2. 检查是否有 operateImage
    if 'content' not in data or 'operateImage' not in data['content']:
        print("Error: JSON 中没有找到 content.operateImage 数据")
        return

    operate_data = data['content']['operateImage']
    
    # 确定输出目录和前缀
    json_dir = os.path.dirname(json_path)
    json_filename = os.path.splitext(os.path.basename(json_path))[0]
    
    # 获取所有的 image 信息
    image_infos = []
    for item in operate_data:
        if isinstance(item, list):
            for img_meta in item:
                if isinstance(img_meta, dict) and 'imageUrl' in img_meta:
                    image_infos.append(img_meta)
        elif isinstance(item, dict) and 'imageUrl' in item:
            image_infos.append(item)
            
    if not image_infos:
        print("Error: 未在 operateImage 中找到任何图片信息 (imageUrl)")
        return
        
    print(f"共发现 {len(image_infos)} 张带有 URL 的图片记录，准备处理...")
    
    for info in image_infos:
        image_id = info.get('imageId')
        image_url = info.get('imageUrl')
        json_w = int(info.get('imageWidth', 0))
        json_h = int(info.get('imageHeight', 0))
        angle = int(info.get('angle', 0))
        
        print(f"\n--- 正在处理 ImageId: {image_id} ---")
        print(f"URL: {image_url}")
        print(f"JSON 设定: 宽={json_w}, 高={json_h}, 角度={angle}")
        
        # 3. 通过内置库自动下载图片到内存中并解码为 cv2 图像
        try:
            req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                img_array = np.asarray(bytearray(response.read()), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is None:
                print(f"Error: 无法解码图片 ImageId {image_id}，可能格式不支持或数据损坏")
                continue
        except Exception as e:
            print(f"Error: 下载图片失败 ImageId {image_id}: {e}")
            continue
            
        current_h, current_w = img.shape[:2]
        print(f"下载的原始图片尺寸: 宽={current_w}, 高={current_h}")
        
        # 4. 旋转逻辑与计算缩放系数
        # 根据你的原逻辑，只打印旋转修正日志和设置角度但不在此硬解码执行，保留它：
        # angle = 0  
        # if (json_w == current_h and json_h == current_w):
        # ...
        
        final_img_h, final_img_w = img.shape[:2]
        
        # 计算缩放比例
        scale_x = final_img_w / json_w if json_w > 0 else 1.0
        scale_y = final_img_h / json_h if json_h > 0 else 1.0
        print(f"缩放比例: X轴={scale_x:.4f}, Y轴={scale_y:.4f}")

        boxes = []
        
        # 辅助方法：提取某个 image_id 相关的所有坐标
        def extract_boxes(item_list, target_id):
            for item in item_list:
                label = item.get('keyDesc', item.get('key', 'Unknown'))
                for source in item.get('sourceList', []):
                    if source.get('imageId') == target_id:
                        bx = source.get('axisX')
                        by = source.get('axisY')
                        bw = source.get('width')
                        bh = source.get('height')
                        
                        if bx is not None:
                            real_x = int(bx * scale_x)
                            real_y = int(by * scale_y)
                            real_w = int(bw * scale_x)
                            real_h = int(bh * scale_y)
                            boxes.append((real_x, real_y, real_w, real_h, label))

        # 5. 从 preDecHead 和 preDecList 提取坐标
        if 'preDecHead' in data['content']:
            extract_boxes(data['content']['preDecHead'], image_id)
        if 'preDecList' in data['content']:
            for row in data['content']['preDecList']:
                extract_boxes(row, image_id)

        print(f"ImageId {image_id} 共绘制 {len(boxes)} 个红框")

        # 6. 在图像上绘制红框
        for (x, y, w, h, label) in boxes:
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
            # （可选）绘制文本标签
            # cv2.putText(img, label[:5], (x, max(y - 5, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

        # 7. 导出至同个目录，并自动命名（解决中文路径无法直接用 imwrite 写出的问题）
        output_path = os.path.join(json_dir, f"{json_filename}_imageId_{image_id}.png")
        # cv2.imwrite 在处理带有中文的路径时往往容易失败返回 False
        # 所以改用 cv2.imencode 然后 tofile 写入
        success, encoded_image = cv2.imencode(".png", img)
        if success:
            encoded_image.tofile(output_path)
            print(f"保存至: {output_path}")
        else:
            print(f"Error: 无法编码并保存图片至 {output_path}")

if __name__ == '__main__':
    # 只需要修改这个 json 路径即可自动打框批量处理
    json_target = r'c:\desktop\YiBao\public\归档\NOSNB25CL48865out.json'
    visualize_all_coordinates(json_target)