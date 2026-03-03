# HS编码相关函数
import requests
import time
import hashlib
import re

def sha1_encrypt(message):
    sha1 = hashlib.sha1()  # 创建一个SHA1哈希对象
    sha1.update(message.encode('utf-8'))  # 将消息转换为UTF-8编码并添加到哈希对象中
    return sha1.hexdigest()  # 返回十六进制数字符串形式的哈希值


def reback(hsCode):
    app_secret = "Tu!ikcIQlctS5Hytc9#Zm2C#?f~qU~BUKN*?wa7v"
    current_time = str(int(time.time() * 1000))
    content = '{"platformId":"ALIYUN01","hsCode":"%s","gName":"","mode":"0"}' % hsCode
    sign = sha1_encrypt("bizCode=DUB00111&bizId=12&content=%s&timestamp=%s&appKey=%s" % (
        content, current_time, app_secret))
    print(f"SHA1 Encrypted gModel: {sign}")
    payload = {"appId": "ZDOCR001", "bizCode": "DUB00111", "bizId": "12",
               "content": content, "timestamp": current_time, "sign": sign}
    response = requests.post("https://openapi-dub.smartebao.com/gateway/receive", data=payload, )
    data = response.json()
    return data

def reback_codeTs(codeTs):
    app_secret = "Tu!ikcIQlctS5Hytc9#Zm2C#?f~qU~BUKN*?wa7v"
    current_time = str(int(time.time() * 1000))
    content = '{"platformId":"ALIYUN01","codeTs":"%s"}' % codeTs
    sign = sha1_encrypt("bizCode=DUB00907&bizId=12&content=%s&timestamp=%s&appKey=%s" % (
        content, current_time, app_secret))
    print(f"SHA1 Encrypted gModel: {sign}")
    payload = {"appId": "ZDOCR001", "bizCode": "DUB00907", "bizId": "12",
               "content": content, "timestamp": current_time, "sign": sign}
    response = requests.post("https://openapi-dub.smartebao.com/gateway/receive", data=payload, )
    data = response.json()
    return data

def get_mainfactor(hsCode):
    print(reback(hsCode)["message"]["resultList"][0]["mainfactor"])
    return reback(hsCode)["message"]["resultList"][0]["mainfactor"]

def get_codeTs(codeTs):
    print(reback_codeTs(codeTs)["message"]["resultList"][0]["codeTs"])

def normalize_value(value):
    """
    处理商品编码：
    1. 分割: 处理 "1;4202920000" 这种带分号的情况。
    2. 清洗: 去除小数点等非数字符号。
    3. 过滤: 丢弃长度小于 4 的纯数字 (视为序号)。
    """
    parts = re.split(r'[;,\/\|\n]+', str(value))  # 支持多种分隔符
    for part in parts:
        part = part.strip()
        if not part:
            continue

        clean_digits = re.sub(r'[^\d]', '', part) # 去除非数字字符
        if len(clean_digits) < 4: #过滤长度小于4
            continue
        if len(clean_digits) > 10:
            clean_digits = clean_digits[:10] # 截断到10位

        return clean_digits

if __name__ == '__main__':
    get_codeTs(normalize_value("abc"))

