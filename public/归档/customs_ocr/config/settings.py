"""
全局配置文件
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# API 配置
API_KEY = os.getenv("API_KEY", "XXXX")
API_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen3-vl-flash"  # 用于图片识别的视觉模型
TEXT_MODEL_NAME = "qwen-flash"  # 用于文本判断的快速模型

# 重试配置
MAX_RETRIES = 3

# 日志配置
LOG_LEVEL = "INFO"
