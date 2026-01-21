import pytesseract
from PIL import Image
import requests
import io
import re


def load_image_from_url(url):
    """
    从 URL 下载图片并转换为 Pillow Image 对象。
    """
    try:
        print(f"正在下载图片: {url}...")
        response = requests.get(url, timeout=15)
        # 检查请求是否成功，如果不成功抛出异常
        response.raise_for_status()
        
        # 将下载的二进制数据转换为字节流
        image_bytes = io.BytesIO(response.content)
        # 使用 Pillow 打开图片
        img = Image.open(image_bytes)
        print("图片下载并加载成功。")
        return img
    except requests.exceptions.RequestException as e:
        print(f"下载图片时出错: {e}")
        return None
    except Exception as e:
        print(f"打开图片时出错: {e}")
        return None

def detect_and_rotate(img):
    """
    使用 Tesseract OSD 检测图片方向，并进行旋转校正。
    """
    try:
        # 1. 调用 Tesseract OSD
        # pytesseract.image_to_osd 默认就会使用 --psm 0 模式
        print("\n正在进行 OSD 方向检测...")
        osd_result_text = pytesseract.image_to_osd(img)
        
        print("--- Tesseract OSD 原始输出 ---")
        print(osd_result_text.strip())
        print("-------------------------------")

        # 2. 解析输出结果，找到需要的旋转角度 (Rotate)
        # 使用正则表达式查找 "Rotate: " 后面的数字
        match = re.search(r'Rotate:\s*(\d+)', osd_result_text)
        
        if match:
            rotation_needed_clockwise = int(match.group(1))
        else:
            print("警告：无法从 OSD 输出中解析出 'Rotate' 值。默认不需要旋转。")
            rotation_needed_clockwise = 0

        print(f"检测结果：需要顺时针旋转 {rotation_needed_clockwise} 度以校正。")

        # 3. 执行旋转
        if rotation_needed_clockwise > 0:
            # 注意：Pillow 的 rotate 方法默认是 *逆时针* 旋转。
            # Tesseract 告诉我们需要 *顺时针* 旋转 X 度。
            # 所以我们需要向 Pillow 传入负值来实现顺时针旋转。
            # expand=True 确保旋转后图像不会被裁剪
            corrected_img = img.rotate(-rotation_needed_clockwise, expand=True)
            print(f"图片已成功顺时针旋转 {rotation_needed_clockwise} 度。")
            return corrected_img
        else:
            print("图片方向正确，无需旋转。")
            return img

    except pytesseract.TesseractError as e:
        print(f"\nTesseract OSD 检测失败: {e}")
        print("可能原因：图片中字符太少、图片过于模糊或没有安装 osd.traineddata。")
        # 如果检测失败，返回原图，避免程序崩溃
        return img
    except Exception as e:
        print(f"发生未知错误: {e}")
        return img

# --- 主程序运行 ---
if __name__ == "__main__":
    # 示例 URL：这是一张被故意倒置（旋转了180度）的图片
    # 你可以替换成你自己的图片 URL 进行测试
    IMAGE_URL = "http://smartebao-production-ocr.oss-cn-shanghai.aliyuncs.com/02504/fa5e446306bd434484aa94ee0b2f3fa7/%E7%AE%B1%E9%97%A81.jpg?x-oss-process=image/auto-orient,0" 

    # 1. 加载图片
    original_image = load_image_from_url(IMAGE_URL)

    if original_image:
        # 可选：显示原始图片以便对比 (需要有图形界面环境)
        # original_image.show(title="原始图片")

        # 2. 检测并校正
        corrected_image = detect_and_rotate(original_image)

        # 3. 保存结果
        output_filename = "/Users/1k/code/YiBao/jyk/TesseractOSD/箱门1.jpg"
        corrected_image.save(output_filename)
        print(f"\n校正后的图片已保存为: {output_filename}")

        # 可选：显示校正后的图片
        # corrected_image.show(title="校正后图片")