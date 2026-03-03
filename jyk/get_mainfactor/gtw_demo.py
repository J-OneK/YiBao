# HS编码相关函数
import requests
import time
import hashlib

def sha1_encrypt(message):
    sha1 = hashlib.sha1()  # 创建一个SHA1哈希对象
    sha1.update(message.encode('utf-8'))  # 将消息转换为UTF-8编码并添加到哈希对象中
    return sha1.hexdigest()  # 返回十六进制数字符串形式的哈希值


def reback():
    app_secret = "Tu!ikcIQlctS5Hytc9#Zm2C#?f~qU~BUKN*?wa7v"
    current_time = str(int(time.time() * 1000))
    content = '{"platformId":"ALIYUN01","hsCode":"6001920000","gName":"","mode":"0"}'
    sign = sha1_encrypt("bizCode=DUB00111&bizId=12&content=%s&timestamp=%s&appKey=%s" % (
        content, current_time, app_secret))
    print(f"SHA1 Encrypted gModel: {sign}")
    payload = {"appId": "ZDOCR001", "bizCode": "DUB00111", "bizId": "12",
               "content": content, "timestamp": current_time, "sign": sign}
    response = requests.post("https://openapi-dub.smartebao.com/gateway/receive", data=payload, )
    data = response.json()
    return data


def reback_codeTs():
    app_secret = "Tu!ikcIQlctS5Hytc9#Zm2C#?f~qU~BUKN*?wa7v"
    current_time = str(int(time.time() * 1000))
    content = '{"platformId":"ALIYUN01","codeTs":"7106911"}'
    sign = sha1_encrypt("bizCode=DUB00907&bizId=12&content=%s&timestamp=%s&appKey=%s" % (
        content, current_time, app_secret))
    print(f"SHA1 Encrypted gModel: {sign}")
    payload = {"appId": "ZDOCR001", "bizCode": "DUB00907", "bizId": "12",
               "content": content, "timestamp": current_time, "sign": sign}
    response = requests.post("https://openapi-dub.smartebao.com/gateway/receive", data=payload, )
    data = response.json()
    return data

if __name__ == '__main__':
    print(reback_codeTs())