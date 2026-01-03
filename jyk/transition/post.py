import json
import time

def transform_source_list(source_list):
    """
    转换 sourceList 中的每一项。
    1. 计算 width 和 height。
    2. 映射坐标字段 (startx/starty -> axisX/axisY)。
    3. 类型转换 (imageId str -> int)。
    4. 添加 processBitMap (默认为 "0")。
    5. 【过滤】彻底移除 extractFrom 等不相关字段。
    """
    transformed = []
    for src in source_list:
        # 计算宽高
        start_x = src.get('startx', 0)
        start_y = src.get('starty', 0)
        end_x = src.get('endx', 0)
        end_y = src.get('endy', 0)
        
        width = end_x - start_x
        height = end_y - start_y
        
        # 转换 imageId 类型
        img_id = src.get('imageId')
        if img_id is not None:
            try:
                img_id = int(img_id)
            except ValueError:
                pass # 如果转换失败保持原样

        new_src = {
            "attTypeCode": src.get('attTypeCode'),
            "imageId": img_id,
            "transformValue": src.get('transformedValue'),
            "originalValue": src.get('value'),
            "normalizedValue": src.get('value'),
            # sourceList 子项也可能有 processBitMap，默认给 "0"
            "processBitMap": src.get('processBitMap', "0"),
            "axisX": start_x,
            "sepValue": src.get('value'),
            "axisY": start_y,
            "width": width,
            "height": height
        }
        
        # 注意：此处不再包含 extractFrom
        
        transformed.append(new_src)
    return transformed

def transform_item(item):
    """
    转换单个字段对象 (preDecHead 或 preDecList 中的项)。
    """
    # 优先使用 transformedValue 作为最终 value 和 normalizedValue
    final_value = item.get('transformedValue', item.get('parsedValue', ''))
    
    new_item = {
        "processBitMap": "0", 
        "sourceList": transform_source_list(item.get('sourceList', [])),
        "source_image": transform_source_list(item.get('sourceList', []))[0].get('imageId'),
        "originalValue": item.get('parsedValue'), # 保留原始 parsedValue
        "normalizedValue": final_value,
        "keyDesc": item.get('keyDesc'),
        "value": final_value,
        "key": item.get('key'),
    }
    # print(transform_source_list(item.get('sourceList', []))[0])
    # 注意：此处不再包含 extractFrom 和 parsedValue (根级别)
    
    return new_item

def main():
    input_file = '/Users/1k/code/YiBao/jyk/transition/output.json'
    output_file = '/Users/1k/code/YiBao/jyk/transition/OCR_merged.json'

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {input_file}")
        return

    # 初始化目标结构
    target_json = {
        "head": {
            "resultCode": "0",
            "resultMessage": "识别成功",
            "version": "1.0",
            "timestampStr": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        },
        "content": {
            "preDecHead": [],
            "preDecList": [],
            "preDecContainer": [], # 保持为空或按需处理
            "extend": {} 
        }
    }

    # 1. 转换 preDecHead
    if "preDecHead" in data:
        for item in data["preDecHead"]:
            target_json["content"]["preDecHead"].append(transform_item(item))

    # 2. 转换 preDecList (嵌套列表)
    if "preDecList" in data:
        for row in data["preDecList"]:
            new_row = []
            for item in row:
                new_row.append(transform_item(item))
            target_json["content"]["preDecList"].append(new_row)

    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(target_json, f, ensure_ascii=False, indent=4)

    print(f"转换完成！结果已保存至: {output_file}")

if __name__ == "__main__":
    main()