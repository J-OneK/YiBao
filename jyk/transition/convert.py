import os
import shutil
import zipfile
import rarfile
import subprocess
from pathlib import Path
from pdf2image import convert_from_path
from PIL import Image
import fitz  # PyMuPDF

# 配置项
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "files/outputs"
LIBREOFFICE_PATH = "/home/jyk/code/YiBao/jyk/transition/LibreOffice_Dir/AppRun"

class FileConverter:
    def __init__(self, output_base_dir=OUTPUT_DIR):
        self.output_base_dir = output_base_dir
        Path(self.output_base_dir).mkdir(parents=True, exist_ok=True)
    
    def process_file(self, file_path):
        file_path = Path(file_path)
        #为每个文件创建单独的输出目录
        output_folder = Path(self.output_base_dir) / file_path.stem
        output_folder.mkdir(parents=True, exist_ok=True)

        suffix = file_path.suffix.lower() # 获取文件后缀名
        
        print(f"----------Processing file: {file_path}, suffix: {suffix}----------")
        try:
            if suffix in ['.zip', '.rar']:
                return self._handle_archive(file_path, output_folder)
            elif suffix in ['.pdf']:
                return self._handle_pdf(file_path, output_folder)
            elif suffix in ['.doc', '.docx', '.xls', '.xlsx']:
                return self._handle_office(file_path, output_folder)
            elif suffix in ['.png', '.jpg', '.jpeg', '.bmp']:
                return self._handle_image(file_path, output_folder)
            else:
                return {"status": "error", "message": "Unsupported file type"}
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            return {"status": "error", "message": str(e)}

    def _handle_image(self, file_path, output_folder):
        img = Image.open(file_path)
        # 统一转换为jpg格式
        output_path = output_folder / f"{file_path.stem}.jpg"
        img.convert("RGB").save(output_path)
        print(f"image size: ", img.size)
        return {"status": "success", "type": "image", "files": [str(output_path)]}
    
    def _handle_pdf(self, file_path, output_folder):
        # 使用PyMuPDF（fitz）
        doc = fitz.open(str(file_path))
        saved_files = []
        # 设定缩放因子
        # PDF 默认是 72 DPI
        zoom_x = 3.0
        zoom_y = 3.0
        mat = fitz.Matrix(zoom_x, zoom_y) #216 DPI
        for i, page in enumerate(doc):
            image = page.get_pixmap(matrix=mat, alpha=False)
            out_path = output_folder / f"image_{i+1}.jpg"
            # print(f"image{i+1} size:", image.width, image.height) # 原始：596 * 842 -> 缩放后：1786 *2526
            image.save(str(out_path))
            saved_files.append(str(out_path))

        doc.close()
        return  {"status": "success", "type": "pdf", "files": saved_files}

        """
        # 使用pdf2image(环境有问题)
        images = convert_from_path(str(file_path), dpi=200)
        saved_files = []
        for i, image in enumerate(images):
            print(f"image{i+1} size:", image.size)
            out_path = output_folder / f"image_{i+1}.jpg"
            image.save(out_path)
            saved_files.append(str(out_path))

        return  {"status": "success", "type": "pdf", "files": saved_files}
        """
    
    def _handle_office(self, file_path, output_folder):
        # 先转pdf再转图片
        # 使用LibreOffice命令行转pdf
        cmd = [
            LIBREOFFICE_PATH, '--headless', '--convert-to', 'pdf',
            '--outdir', str(output_folder), str(file_path)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # 找到pdf后转图片
        pdf_filename = file_path.stem + ".pdf"
        pdf_path = output_folder / pdf_filename

        if pdf_path.exists():
            return self._handle_pdf(pdf_path, output_folder)
        else:
            raise Exception("Failed to convert Office document to PDF")

if __name__ == "__main__":
    fc = FileConverter()
    result = fc.process_file("/home/jyk/code/YiBao/jyk/transition/files/excel/W6787UA0161.xls")
    print(result)