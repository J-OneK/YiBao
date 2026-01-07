import pandas as pd
import dataframe_image as dfi
import os
import re
import requests
from io import BytesIO

def sanitize_filename(filename):
    """处理非法字符，确保 Sheet 名可以作为文件名"""
    return re.sub(r'[\\/*?:"<>|]', "_", filename)

def excel_to_images(excel_url_or_path, output_folder, max_rows=30):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    print(f"正在读取文件: {excel_url_or_path}")

    # 1. 自动判断是本地文件还是 URL
    if excel_url_or_path.startswith('http'):
        # 针对阿里云OSS等URL，先下载到内存中
        response = requests.get(excel_url_or_path)
        response.raise_for_status() # 如果下载失败会报错
        file_content = BytesIO(response.content)
    else:
        file_content = excel_url_or_path

    # 2. 读取所有 Sheets
    # engine='xlrd' 用于处理 .xls, engine='openpyxl' 用于处理 .xlsx
    # 不指定 engine 时 pandas 会自动根据后缀选择，前提是库都装好了
    try:
        sheets_dict = pd.read_excel(file_content, sheet_name=None)
    except Exception as e:
        print(f"读取 Excel 失败: {e}")
        return

    for sheet_name, df in sheets_dict.items():
        print(f"正在处理工作表: {sheet_name}")
        
        # 过滤掉非法文件名字符
        safe_sheet_name = sanitize_filename(sheet_name)

        # 3. 需求1：去除四周的空白单元格
        # 去除全空的行和列
        df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
        
        if df.empty:
            print(f"  -> 跳过空表: {sheet_name}")
            continue

        df = df.reset_index(drop=True)
        total_rows = len(df)

        # 4. 需求2：如果表格很大，进行切分处理
        if total_rows <= max_rows:
            output_path = os.path.join(output_folder, f"{safe_sheet_name}.png")
            # table_conversion='chrome' 渲染效果最好，但需要安装 Chrome
            dfi.export(df, output_path, table_conversion='chrome')
            print(f"  -> 已生成: {output_path}")
        else:
            start_row = 0
            part_num = 1
            while start_row < total_rows:
                end_row = min(start_row + max_rows, total_rows)
                df_chunk = df.iloc[start_row:end_row]
                
                output_path = os.path.join(output_folder, f"{safe_sheet_name}_Part_{part_num}.png")
                
                # 导出图片，每一部分都会自动带上表头
                dfi.export(df_chunk, output_path, table_conversion='chrome')
                print(f"  -> 已生成: {output_path} (第 {part_num} 部分)")
                
                start_row = end_row
                part_num += 1

if __name__ == "__main__":
    # 你的阿里云 URL
    target_url = "http://smartebao-production-ocr.oss-cn-shanghai.aliyuncs.com/02509/665620d23ccd47bf942616a99dbe9886/ONEYNB5BFM160400A/ONEYNB5BFM160400A/%E6%8A%A5%E5%85%B3%E8%B5%84%E6%96%99-ONEYNB5BFM160400-TM202507005232-%E8%87%B4%E6%AC%A7%E9%A2%86%E6%9C%AA-US250660WH-1.xls"
    
    target_dir = "./result_imgs"
    
    excel_to_images(target_url, target_dir, max_rows=30)