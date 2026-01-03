import json
import os
from collections import OrderedDict

# ==============================================================================
# 1. HEAD 节点配置 (可在此处修改全局变量)
# ==============================================================================
HEAD_BIZ_CODE = "DUB00113"
HEAD_APP_ID = "ALIYUN01"
HEAD_BIZ_ID = "E68b65fb4c513f93352973802"
HEAD_RESULT_CODE = "0"
HEAD_MSG_ID = "928176773"
HEAD_RESULT_MESSAGE = "识别成功"
HEAD_VERSION = "1.0"
HEAD_TIMESTAMP = "2025-09-02 11:09:27"
HEAD_RECEIVE_ID = "EBAO0001"
HEAD_SIGN_INFO = ""
HEAD_RECEIPT_TYPE = 0

# ==============================================================================
# 2. 字段映射配置 (来源: field_mapping.py)
# ==============================================================================
# 资料类型代码到名称的映射
ATT_TYPE_NAMES = {
    1: "合同",
    2: "发票",
    3: "装箱单",
    4: "预录入单",
    5: "申报要素",
    14: "电子底账",
    15: "提/运单",
    19: "空运运单",
    6: "仓库清单",
    7: "舱单",
    8: "通关单",
    9: "委托书",
    10: "许可证",
    11: "产地证",
    12: "进港箱单",
    13: "其他",
    17: "核注清单",
    18: "快件运单",
    21: "配载清单",
    22: "入港通知",
    23: "预配/订舱",
    24: "船代单"
}

# ==============================================================================
# 3. 核心逻辑
# ==============================================================================

def get_head_node():
    """构造 head 节点数据"""
    return {
        "signInfo": HEAD_SIGN_INFO,
        "receiptType": HEAD_RECEIPT_TYPE,
        "bizCode": HEAD_BIZ_CODE,
        "appId": HEAD_APP_ID,
        "bizId": HEAD_BIZ_ID,
        "resultCode": HEAD_RESULT_CODE,
        "msgId": HEAD_MSG_ID,
        "resultMessage": HEAD_RESULT_MESSAGE,
        "version": HEAD_VERSION,
        "timestampStr": HEAD_TIMESTAMP,
        "receiveId": HEAD_RECEIVE_ID
    }

def clean_and_transform(data):
    """
    递归遍历数据结构，执行删除字段和值转换的操作
    """
    if isinstance(data, dict):
        new_data = {}
        for key, value in data.items():
            # --- 删除规则 ---
            
            # 规则 6: if_unify 字段直接剔除
            if key == 'if_unify':
                continue
            
            # 规则 3: content中可以删除 nlpRes 字段
            if key == 'nlpRes':
                continue

            # 规则 2 & 3: 删除 parsedValue, extractFrom (出现在 extend, preDecHead, sourceList 等中)
            if key in ['parsedValue', 'extractFrom']:
                continue

            # 规则 3: sourceList 中的 creditLevel, sepValueList 删除
            if key in ['creditLevel', 'sepValueList']:
                continue

            # 规则 2: operateImage 字段节点中的特定字段删除
            if key in ['callOcrOpen', 'extractSource', 'preAttTypeCode', 
                       'parseCode', 'inputDocType', 'classifySource']:
                continue

            # --- 转换规则 ---

            # 规则 5: attTypeCode 字段转成类型名称
            if key == 'attTypeCode':
                # 如果值在映射表中，则转换；否则保留原值
                if isinstance(value, int) and value in ATT_TYPE_NAMES:
                    new_data[key] = ATT_TYPE_NAMES[value]
                else:
                    new_data[key] = value
                continue

            # --- 递归处理 ---
            new_data[key] = clean_and_transform(value)
        
        return new_data

    elif isinstance(data, list):
        # 如果是列表，递归处理列表中的每一项
        return [clean_and_transform(item) for item in data]
    
    else:
        # 基本数据类型直接返回
        return data

def extract_extend_fields(content_data):
    """
    从 cleaned content 中提取 plNetWt, inAmount, contrAmount 到 extend 节点
    """
    # 初始化 extend 数据结构
    extend_node = {
        "plNetWtList": [],
        "inAmountList": [],
        "contrAmountList": []
    }

    # 映射关系: 原字段 key -> extend 中的 list key
    key_mapping = {
        "gnetWt": "plNetWtList",
        "totalAmount": "inAmountList",
        "declTotal": "contrAmountList"
    }

    # 在 preDecHead 中查找对应字段
    if "preDecHead" in content_data and isinstance(content_data["preDecHead"], list):
        for item in content_data["preDecHead"]:
            if isinstance(item, dict) and "key" in item:
                item_key = item["key"]
                print(item_key)
                if item_key in key_mapping:
                    target_list = key_mapping[item_key]
                    # 将找到的项（已经是清洗过的）添加到对应的列表中
                    extend_node[target_list].append(item)

    # 2. 在 preDecList (列表的列表) 中查找
    # preDecList 结构通常是 [[{col1}, {col2}], [{col1}, {col2}]]
    if "preDecList" in content_data and isinstance(content_data["preDecList"], list):
        for row in content_data["preDecList"]:
            if isinstance(row, list):
                for item in row:
                    if isinstance(item, dict) and "key" in item:
                        item_key = item["key"]
                        print(item_key)
                        if item_key in key_mapping:
                            target_list = key_mapping[item_key]
                            extend_node[target_list].append(item)
    
    return extend_node

def main():
    input_filename = '/Users/1k/code/YiBao/jyk/归档/customs_ocr/output.json'
    output_filename = '/Users/1k/code/YiBao/jyk/transition/OCRoutput.json'

    # 1. 读取 output.json
    if not os.path.exists(input_filename):
        print(f"错误: 找不到文件 {input_filename}")
        return

    try:
        with open(input_filename, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except json.JSONDecodeError:
        print(f"错误: {input_filename} 不是有效的 JSON 格式")
        return

    # 2. 全局清洗和转换 (attTypeCode, 删除字段等)
    cleaned_content = clean_and_transform(raw_data)
    # print(cleaned_content)
    # 3. 提取 extend 数据
    # 注意：此时 cleaned_content 已经是处理过的，所以提取出来的数据也是处理过的
    new_extend_node = extract_extend_fields(cleaned_content)
    
    # 4. 合并 extend 节点
    # 如果原 content 中已有 extend，我们将其与新提取的合并（优先使用提取的列表）
    final_extend = {}
    if "extend" in cleaned_content and isinstance(cleaned_content["extend"], dict):
        final_extend = cleaned_content["extend"]
    
    # 更新/覆盖特定的 list 字段
    final_extend.update(new_extend_node)

    # 5. 构造最终的 content 结构，确保 extend 排在第一位
    final_content = OrderedDict()
    final_content["extend"] = final_extend
    
    # 将 cleaned_content 中的其他字段加入，跳过原来的 'extend' (因为已经处理过了)
    for key, value in cleaned_content.items():
        if key != "extend":
            final_content[key] = value

    # 6. 构造最终 JSON
    final_json = {
        "head": get_head_node(),
        "content": final_content
    }

    # 7. 写入文件
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_json, f, ensure_ascii=False, indent=4)
        print(f"转换成功！已生成文件: {output_filename}")
    except Exception as e:
        print(f"写入文件时发生错误: {e}")

if __name__ == "__main__":
    main()