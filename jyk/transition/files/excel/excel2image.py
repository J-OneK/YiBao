import pandas as pd
from playwright.sync_api import sync_playwright
import os
import cv2

def excel_to_image_via_browser(file_path, sheet_name, output_image):
    # 1. 读取 .xls 文件
    df = pd.read_excel(file_path, sheet_name=sheet_name, engine='xlrd')
    
    # 将 DataFrame 转换为 HTML，处理空值为无
    html_table = df.to_html(index=False, na_rep="")
    
    # 2. 构造带 CSS 的完整 HTML (解决字段过长显示不全的关键)
    styled_html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ margin: 0; padding: 20px; background-color: white; }}
            table {{ 
                border-collapse: collapse; 
                width: 1200px; /* 锁定宽度，让 VLM 识别更稳定 */
                table-layout: fixed; 
                font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
            }}
            th, td {{ 
                border: 1px solid #333; 
                padding: 10px; 
                word-wrap: break-word; /* 强制换行 */
                font-size: 14px; 
                line-height: 1.5;
            }}
            th {{ background-color: #f5f5f5; }}
            /* 你可以根据需要调整特定列的宽度，比如第二列是英文品名 */
            td:nth-child(2) {{ width: 350px; }}
        </style>
    </head>
    <body>
        {html_table}
    </body>
    </html>
    """

    # 3. 启动无头浏览器进行截图
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        # 设置较大的视口高度以容纳长单据
        page.set_viewport_size({"width": 1300, "height": 800})
        page.set_content(styled_html)
        
        # 等待内容加载完成
        page.wait_for_load_state("networkidle")
        
        # 精准定位表格进行截图（彻底解决多余留白问题）
        element = page.locator("table")
        element.screenshot(path=output_image, animations="disabled")
        
        browser.close()
    print(f"转换成功：{output_image}")

# 运行
input_file = "/Users/1k/code/YiBao/jyk/transition/files/excel/报关资料-ONEYNB5BFM160400-TM202507005232-致欧领未-US250660WH-1.xls"
output_path = "/Users/1k/code/YiBao/jyk/transition/files/excel/output_报关资料.png"
excel_to_image_via_browser(input_file, "报关单", output_path)

img = cv2.imread(output_path)
print(img.shape)