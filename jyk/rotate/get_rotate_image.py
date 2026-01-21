import json
import os
import glob

def process_json_files(input_folder, output_filename):
    """
    遍历文件夹读取JSON，提取angle不为0的图片信息
    """
    extracted_data = []
    
    # 获取文件夹下所有json文件的路径
    json_files = glob.glob(os.path.join(input_folder, '*.json'))
    
    print(f"找到 {len(json_files)} 个JSON文件，开始处理...")

    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 安全地获取 operateImage 列表
                # 结构为 root -> content -> operateImage
                content = data.get('content', {})
                if not content:
                    continue
                    
                operate_image_list = content.get('operateImage', [])
                
                if not isinstance(operate_image_list, list):
                    continue

                # 遍历 operateImage 列表中的每一项
                for item in operate_image_list:
                    angle = item.get('angle', 0)
                    att_type_code = item.get('attTypeCode', 0)
                    # 核心逻辑：只有当 angle 存在且不等于 0 时才提取
                    if angle != 0 and att_type_code in [1,2,3,4,5,14,15,19]:
                        entry = {
                            "sourceFile": os.path.basename(file_path), # 记录来源文件名，方便追溯
                            "imageUrl": item.get('imageUrl', ''),
                            "angle": angle,
                            "imageWidth": item.get('imageWidth', ''),
                            "imageHeight": item.get('imageHeight', '')
                        }
                        extracted_data.append(entry)
                        
        except json.JSONDecodeError:
            print(f"错误: 无法解析文件 {file_path}")
        except Exception as e:
            print(f"处理文件 {file_path} 时发生未知错误: {str(e)}")

    # 将结果保存为JSON文件
    try:
        with open(output_filename, 'w', encoding='utf-8') as f_out:
            json.dump(extracted_data, f_out, indent=4, ensure_ascii=False)
        print(f"处理完成！")
        print(f"共提取 {len(extracted_data)} 条数据。")
        print(f"结果已保存至: {output_filename}")
    except IOError as e:
        print(f"保存结果文件失败: {str(e)}")

# ================= 配置区域 =================
if __name__ == "__main__":
    # 1. 请将此处修改为你存放JSON文件的文件夹路径
    # 例如: input_dir = "C:/Users/Admin/Documents/jsons" 或 "./data"
    input_dir = "/Users/1k/易豹/OCR" 
    # 2. 输出文件的名称
    output_file = "/Users/1k/code/YiBao/jyk/rotate/rotation_dataset.json"

    # 检查输入目录是否存在
    if not os.path.exists(input_dir):
        print(f"错误: 找不到文件夹 '{input_dir}'，请在代码中修改 input_dir 变量。")
    else:
        process_json_files(input_dir, output_file)