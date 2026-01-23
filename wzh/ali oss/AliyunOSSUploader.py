import oss2
import os
import datetime
import hashlib
from typing import Optional


class AliyunOSSUploader:
    """阿里云OSS文件上传工具类，返回完整OSS访问路径"""

    def __init__(self,
                 access_key_id: str,
                 access_key_secret: str,
                 bucket_name: str,
                 public_endpoint: str):
        """
        初始化OSS上传器
        :param access_key_id: 阿里云AccessKey ID
        :param access_key_secret: 阿里云AccessKey Secret
        :param bucket_name: OSS Bucket名称
        :param public_endpoint: OSS公网Endpoint
        """
        self.auth = oss2.Auth(access_key_id, access_key_secret)
        self.bucket = oss2.Bucket(self.auth, public_endpoint, bucket_name)
        self.public_endpoint = public_endpoint
        self.bucket_name = bucket_name
        # 固定路径前缀（可自行定义，建议规范定义oss上文件夹路径，便于后期管理）
        self.base_oss_prefix = "ocr/operateImage"

    def _get_today_date_str(self) -> str:
        """获取当前日期，格式化为YYYY-MM-DD"""
        return datetime.datetime.now().strftime("%Y-%m-%d")

    def _generate_dynamic_oss_path(self, filename: str) -> str:
        """
        动态生成OSS路径：ocr/operateImage/YYYY-MM-DD/文件名
        :param filename: 上传的文件名（如temp.jpg）
        :return: 完整的OSS相对路径
        """
        today_date = self._get_today_date_str()
        # 拼接动态路径，自动处理文件名前后的多余斜杠（可自行定义，建议规范定义oss上文件夹路径，便于后期管理）
        oss_file_path = os.path.join(self.base_oss_prefix, today_date, filename).replace("\\", "/")
        return oss_file_path

    def _get_full_oss_path(self, oss_file_path: str) -> str:
        """拼接完整的OSS公网访问路径"""
        clean_oss_path = oss_file_path.lstrip('/')
        full_path = f"https://{self.bucket_name}.{self.public_endpoint}/{clean_oss_path}"
        return full_path

    def _get_file_md5(self, file_path: str) -> str:
        """
        计算文件的MD5值
        :param file_path: 文件路径
        :return: 32位MD5字符串
        """
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def upload_file(self,
                    local_file_path: str,
                    target_filename: str = None,
                    use_md5_filename: bool = False,
                    preserve_original_name: bool = True,
                    original_filename: str = None,
                    chunk_size: int = 10 * 1024 * 1024) -> Optional[str]:
        """
        上传本地文件到OSS（动态日期路径），返回完整公网访问路径
        :param local_file_path: 本地文件绝对路径（如D:/temp.jpg）
        :param target_filename: OSS上的最终文件名（如temp.jpg），如果use_md5_filename=True则此参数可不传
        :param use_md5_filename: 是否使用文件MD5作为文件名（推荐，可防止重名覆盖）
        :param preserve_original_name: 使用MD5文件名时，是否保留原文件名用于下载（默认True）
        :param original_filename: 指定用于Content-Disposition的原始文件名（可选）
        :param chunk_size: 分片上传块大小（默认10MB）
        :return: 上传成功返回完整OSS路径，失败返回None
        """
        try:
            # 检查本地文件是否存在
            if not os.path.exists(local_file_path):
                raise FileNotFoundError(f"本地文件不存在：{local_file_path}")

            # 确定用于Content-Disposition的原始文件名
            if original_filename is None:
                original_filename = os.path.basename(local_file_path)
            
            # 如果启用MD5文件名，自动生成
            if use_md5_filename:
                file_ext = os.path.splitext(local_file_path)[1]  # 获取文件扩展名
                md5_value = self._get_file_md5(local_file_path)
                target_filename = f"{md5_value}{file_ext}"
                print(f"使用MD5文件名：{target_filename}")
                if preserve_original_name:
                    print(f"下载时将使用原文件名：{original_filename}")
            elif not target_filename:
                # 如果没有指定文件名且不使用MD5，则使用原文件名
                target_filename = os.path.basename(local_file_path)

            # 动态生成OSS路径
            oss_file_path = self._generate_dynamic_oss_path(target_filename)
            file_size = os.path.getsize(local_file_path)

            # 准备HTTP响应头（用于控制下载时的文件名）
            headers = {}
            if use_md5_filename and preserve_original_name:
                # 设置Content-Disposition，浏览器下载时使用原文件名
                headers['Content-Disposition'] = f'attachment; filename="{original_filename}"'

            # 小文件直传（<100MB）
            if file_size < 100 * 1024 * 1024:
                self.bucket.put_object_from_file(oss_file_path, local_file_path, headers=headers)
                print(f"小文件上传成功！OSS相对路径：{oss_file_path}")

            # 大文件分片上传（≥100MB）
            else:
                upload_id = self.bucket.init_multipart_upload(oss_file_path, headers=headers).upload_id
                parts = []
                with open(local_file_path, 'rb') as f:
                    part_number = 1
                    while True:
                        data = f.read(chunk_size)
                        if not data:
                            break
                        part = self.bucket.upload_part(oss_file_path, upload_id, part_number, data)
                        parts.append(oss2.models.PartInfo(part_number, part.etag))
                        part_number += 1
                self.bucket.complete_multipart_upload(oss_file_path, upload_id, parts, headers=headers)
                print(f"大文件分片上传成功！OSS相对路径：{oss_file_path}")

            # 返回完整OSS公网路径
            full_oss_path = self._get_full_oss_path(oss_file_path)
            return full_oss_path

        except FileNotFoundError as e:
            print(f"上传失败：{e}")
            return None
        except oss2.exceptions.OssError as e:
            print(f"OSS服务错误：{e}")
            return None
        except Exception as e:
            print(f"未知上传错误：{e}")
            return None


# ---------------------- 调用示例 ----------------------
if __name__ == "__main__":
    # 阿里云OSS配置读取（优先级：本地配置文件 > 环境变量）
    # 方式1：从本地配置文件读取（推荐）
    #   创建 oss_config.py 文件，定义 OSS_CONFIG 字典
    # 方式2：从环境变量读取
    #   Windows: set OSS_ACCESS_KEY_ID=你的ID
    #            set OSS_ACCESS_KEY_SECRET=你的Secret
    
    import os
    
    # 尝试从本地配置文件读取
    try:
        from oss_config import OSS_CONFIG
        CONFIG = OSS_CONFIG
        print("✓ 从本地配置文件读取OSS凭证")
    except ImportError:
        # 如果没有配置文件，从环境变量读取
        CONFIG = {
            "access_key_id": os.getenv("OSS_ACCESS_KEY_ID", ""),
            "access_key_secret": os.getenv("OSS_ACCESS_KEY_SECRET", ""),
            "bucket_name": "smartebao-dub-zd-ocr",
            "public_endpoint": "oss-cn-shanghai.aliyuncs.com"
        }
        
        # 检查凭证是否已设置
        if not CONFIG["access_key_id"] or not CONFIG["access_key_secret"]:
            print("❌ 错误：未找到OSS凭证配置")
            print("\n请选择以下任一方式配置：")
            print("1. 创建 oss_config.py 文件（推荐）")
            print("2. 设置环境变量 OSS_ACCESS_KEY_ID 和 OSS_ACCESS_KEY_SECRET")
            exit(1)
        print("✓ 从环境变量读取OSS凭证")

    # 初始化上传器
    oss_uploader = AliyunOSSUploader(
        access_key_id=CONFIG["access_key_id"],
        access_key_secret=CONFIG["access_key_secret"],
        bucket_name=CONFIG["bucket_name"],
        public_endpoint=CONFIG["public_endpoint"]
    )

    # 配置上传参数
    LOCAL_FILE_PATH = r"C:\desktop\YiBao\jyk\rotate\final_corrected_output.jpg"  # 本地文件绝对路径

    # 方式1：使用MD5作为文件名 + 保留原文件名用于下载（推荐，防止文件名重复覆盖）
    # OSS存储名：79c8630f9ba9bff35bfd9a4108c068d4.jpg
    # 浏览器下载时自动命名为：final_corrected_output.jpg
    full_oss_path = oss_uploader.upload_file(LOCAL_FILE_PATH, use_md5_filename=True, preserve_original_name=True)

    # 方式2：仅使用MD5，下载时也是MD5名称
    # full_oss_path = oss_uploader.upload_file(LOCAL_FILE_PATH, use_md5_filename=True, preserve_original_name=False)

    # 方式3：自定义文件名
    # TARGET_FILENAME = "final_corrected_output.jpg"
    # full_oss_path = oss_uploader.upload_file(LOCAL_FILE_PATH, TARGET_FILENAME)

    # 方式4：使用原文件名
    # full_oss_path = oss_uploader.upload_file(LOCAL_FILE_PATH)

    if full_oss_path:
        print(f"文件上传成功！完整OSS公网路径：{full_oss_path}")
    else:
        print("文件上传失败，未获取到OSS路径！")