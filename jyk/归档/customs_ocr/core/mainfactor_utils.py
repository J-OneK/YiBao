import json
import re
import requests
import time
import hashlib


# ------------------------------------------从第一轮结果得到所有商品编号------------------------------------------
def get_codets_values(data_dict):
    """
    从第一轮识别结果dict中提取所有codeTs字段的parsedValue值列表
    """
    values = []
    try:
        # 1. 检查 preDecList 是否存在
        if 'preDecList' not in data_dict:
            return None
    
        # 2. 遍历外层列表（代表每一行商品）
        for row in data_dict['preDecList']:
            # 3. 遍历内层列表（代表行内的具体字段）
            for item in row:
                # 4. 找到 key 为 'codeTs' 的字典
                if item.get('key') == 'codeTs':
                    # 5. 获取 sourceList 中的值
                    source_list = item.get('sourceList', [])
                    if source_list:
                        # 返回第一个元素的 value 值
                        values.append(source_list[0].get('value'))
        return values               
    except Exception as e:
        print(f"读取出错: {e}")        


def normalize_values(values):
    """
    处理得到的商品编码列表（不重复）：
    1. 分割: 处理 "1;4202920000" 这种带分号的情况。
    2. 清洗: 去除小数点等非数字符号。
    3. 过滤: 丢弃长度小于 4 的纯数字 (视为序号)。
    4. 补全: 不足 10 位后补 0。
    """
    valid_values = []
    for v in values:
        parts = re.split(r'[;,\/\|\n]+', str(v))  # 支持多种分隔符
        for part in parts:
            part = part.strip()
            if not part:
                continue

            clean_digits = re.sub(r'[^\d]', '', part) # 去除非数字字符
            if len(clean_digits) < 4: #过滤长度小于4
                continue
            if len(clean_digits) > 10:
                clean_digits = clean_digits[:10] # 截断到10位
            elif len(clean_digits) < 10:
                clean_digits = clean_digits.ljust(10, '0') # 补全到10位
            
            valid_values.append(clean_digits)

    seen = set()
    unique_values = [x for x in valid_values if not (x in seen or seen.add(x))]
    return unique_values

# ------------------------------------------调用易豹对应接口得到mainfactor字段------------------------------------------

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

def get_mainfactor(hsCode):
    if "resultList" not in reback(hsCode)["message"]:
        print(f"HS编码 {hsCode} 未找到对应的申报要素信息！")
        return ""
    return reback(hsCode)["message"]["resultList"][0]["mainfactor"]
