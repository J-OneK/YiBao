import json

def merge_declaration_factors_strict_order(data, factor_list):
    """
    将申报要素合并到 preDecList 中。
    严格保证字典 Key 的顺序：
    外层: keyDesc -> key -> sourceList
    内层: value -> pixel -> imageId
    """
    # 1. 建立映射字典
    factors_map = {item['codeTs']: item for item in factor_list}
    
    pre_dec_list = data.get('preDecList', [])

    for item_list in pre_dec_list:
        current_code_ts = None
        
        # 2. 获取当前商品的 codeTs
        for field in item_list:
            if field.get('key') == 'codeTs':
                source_list = field.get('sourceList', [{}])
                if source_list:
                    current_code_ts = source_list[0].get('value')
                break
        
        # 3. 如果匹配到申报要素，构造符合顺序的新字典
        if current_code_ts and current_code_ts in factors_map:
            target_factor = factors_map[current_code_ts]
            
            # --- 步骤 A: 构建内层字典 (按照 value -> pixel -> imageId 顺序) ---
            new_source_item = {
                'value': target_factor['mainfactors'],
                'pixel': target_factor['pixel'],
                'imageId': target_factor['imageId']
            }
            
            # --- 步骤 B: 构建外层字典 (按照 keyDesc -> key -> sourceList 顺序) ---
            # 注意：如果原数据中 gModel 的 keyDesc 叫其他名字（极少见），这里统一重置为 '规格型号'
            new_gmodel_field = {
                'keyDesc': '规格型号',
                'key': 'gModel',
                'sourceList': [new_source_item]
            }

            # --- 步骤 C: 替换或追加 ---
            gmodel_index = -1
            for i, field in enumerate(item_list):
                if field.get('key') == 'gModel':
                    gmodel_index = i
                    break
            
            if gmodel_index != -1:
                # 如果存在，直接替换整个字典对象，以保证 Key 的顺序完全重置
                item_list[gmodel_index] = new_gmodel_field
            else:
                # 如果不存在，追加到末尾
                item_list.append(new_gmodel_field)

    return data

# ==========================================
# 测试验证
# ==========================================

source_data = {
    'preDecHead': [], 
    'preDecList': [[
        {'keyDesc': '商品编号', 'key': 'codeTs', 'sourceList': [{'value': '9406900090', 'pixel': [65, 401, 142, 413], 'imageId': '3'}]}, 
        # 模拟一个乱序的旧数据，测试是否会被修正顺序
        {'key': 'gModel', 'sourceList': [{'imageId': '99', 'pixel': [0,0,0,0], 'value': '旧值'}], 'keyDesc': '规格型号'} 
    ]]
}

factors_data = [{
    'codeTs': '9406900090', 
    'mainfactors': '0|0|铝合金|塑料底盘，内部配置：花洒|90 x 90x 210CM|null|null', 
    'pixel': [147, 431, 520, 508], 
    'imageId': '3' 
}]

# 执行合并
result = merge_declaration_factors_strict_order(source_data, factors_data)

# 打印结果 (使用 json.dumps 可以清楚看到 Key 的顺序)
print(json.dumps(result['preDecList'], ensure_ascii=False, indent=4))