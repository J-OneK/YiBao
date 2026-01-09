"""
字段映射配置
根据"报关单识别资料分类及字段提取说明_新.xlsx"文件中的字段定义生成
"""

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

ATT_TYPE_NAMES_EN = {
    1: "Contract",
    2: "Invoice",
    3: "PackingList",
    4: "Declaration",
    5: "Attributes",
    14: "Bill",
    15: "ExpressFedex",
    19: "ExpressShanghaiPuhuo",
    6: "Warehouse Inventory List",
    7: "Manifest",
    8: "Customs Clearance Certificate",
    9: "Power of Attorney",
    10: "License/Permit",
    11: "Certificate of Origin",
    12: "Port-in Container List",
    13: "Other",
    17: "Inventory Collection List",
    18: "Express Waybill",
    21: "Stowage Plan",
    22: "Port Entry Notice",
    23: "Booking Confirmation",
    24: "Shipping Agency Document"
}

# 中文字段名到英文 key 的映射
KEY_DESC_TO_KEY = {
    # 表头字段
    "主运单号": "mainBillNo",
    "件数": "packNo",
    "保费币制": "insurCurr",
    "保费标记": "insurMark",
    "保费率": "insurRate",
    "净重": "netWt",
    "出境关别": "iEPort",
    "包装种类": "wrapType",
    "合同协议号": "contrNo",
    "境内收发货人名称": "consigneeCname",
    "境内收发货人海关代码": "rcvgdTradeCode",
    "境内收发货人社会信用代码": "rcvgdTradeScc",
    "境外收发货人": "consignorEname",
    "备案号": "manualNo",
    "存放地点": "GoodsPlace",
    "征免性质": "cutMode",
    "总价总和": "totalAmount",
    "成交方式": "transMode",
    "指运港": "distinatePort",
    "提运单号": "billNo",
    "杂费币制": "otherCurr",
    "杂费标记": "otherMark",
    "杂费率": "otherRate",
    "标记唛码及备注": "noteS",
    "毛重": "grossWt",
    "生产销售单位名称": "ownerName",
    "生产销售单位海关代码": "ownerCode",
    "生产销售单位社会信用代码": "ownerScc",
    "监管方式": "supvModeCode",
    "离境口岸": "ciqEntyPortCode",
    "许可证号": "licenseNo",
    "贸易国": "cusTradeNationCode",
    "运抵国": "cusTradeCountry",
    "运费币制": "feeCurr",
    "运费标记": "feeMark",
    "运费率": "feeRate",
    "运输方式": "cusTrafMode",
    "随附单证及编号": "Edoc",
    "页码页数": "pageNo",
    
    # 表体字段
    "件数单项": "gpackNo",
    "净重单项": "gnetWt",
    "单价": "declPrice",
    "原产国": "cusOriginCountry",
    "商品名称": "gName",
    "商品编号": "codeTs",
    "境内货源地": "districtCode",
    "币制": "tradeCurr",
    "征免": "dutyMode",
    "总价": "declTotal",
    "成交单位": "gUnit",
    "成交数量": "gQty",
    "最终目的国": "destinationCountry",
    "毛重单项": "ggrossWt",
    "法定第一数量": "qty1",
    "法定第二数量": "qty2",
    "规格型号": "gModel",
    
    # 集装箱
    "柜号": "containerNo",
    
    # 随附单证
    "单证代码": "acmpFormCode",
    "单证编号": "acmpFormNo",
    
    # 扩展字段
    "合同商品总价": "contrAmount",
    "发票商品总价": "inAmount",
    "装箱单商品净重": "plNetWt",
    
    # 添加大模型可能输出的变体名称映射
    "发票号": "licenseNo",
    "发票号 NO.": "licenseNo",
    "日期": "pageNo",
    "日期 DATE": "pageNo",
    "柜型": "containerNo",
    "毛重（千克）": "grossWt",
    "净重（千克）": "netWt",
    "运费": "feeRate",
    "保费": "insurRate",
    "杂费": "otherRate",
    "贸易国（地区）": "cusTradeNationCode",
    "运抵国（地区）": "cusTradeCountry",
    "运输工具名称及航次号": "trafName",
    "出口日期": "pageNo",
    "申报日期": "pageNo",
    "页码/页数": "pageNo"
}

# 不同文件类型对应的表头字段（preDecHead）
HEAD_FIELDS_BY_TYPE = {
    1: [  # 合同
        "保费币制", "保费标记", "保费率", "境内收发货人名称", "境内收发货人海关代码",
        "境内收发货人社会信用代码", "境外收发货人", "备案号", "总价总和", "成交方式",
        "指运港", "杂费币制", "杂费标记", "杂费率", "生产销售单位名称",
        "生产销售单位海关代码", "生产销售单位社会信用代码", "贸易国", "运抵国",
        "运费币制", "运费标记", "运费率", "合同协议号", "柜号"
    ],
    2: [  # 发票
        "保费币制", "保费标记", "保费率", "境内收发货人名称", "境内收发货人海关代码",
        "境内收发货人社会信用代码", "境外收发货人", "备案号", "总价总和", "成交方式",
        "指运港", "杂费币制", "杂费标记", "杂费率", "生产销售单位名称",
        "生产销售单位海关代码", "生产销售单位社会信用代码", "贸易国", "运抵国",
        "运费币制", "运费标记", "运费率", "合同协议号", "柜号"
    ],
    3: [  # 装箱单
        "件数", "包装种类", "境内收发货人名称", "境内收发货人海关代码",
        "境内收发货人社会信用代码", "境外收发货人", "备案号", "指运港",
        "毛重", "生产销售单位名称", "生产销售单位海关代码", "生产销售单位社会信用代码",
        "贸易国", "运抵国", "净重", "柜号"
    ],
    4: [  # 预录入单
        "件数", "保费币制", "保费标记", "保费率", "净重", "出境关别",
        "包装种类", "合同协议号", "境内收发货人名称", "境内收发货人海关代码",
        "境内收发货人社会信用代码", "境外收发货人", "备案号", "存放地点",
        "征免性质", "成交方式", "指运港", "提运单号", "杂费币制", "杂费标记",
        "杂费率", "标记唛码及备注", "毛重", "生产销售单位名称", "生产销售单位海关代码",
        "生产销售单位社会信用代码", "监管方式", "离境口岸", "许可证号", "贸易国",
        "运抵国", "运费币制", "运费标记", "运费率", "运输方式", "随附单证及编号", "页码页数", "柜号"
    ],
    5: [  # 申报要素
        "境内收发货人名称"
    ],
    14: [  # 电子底账
        "合同协议号", "境内收发货人名称", "监管方式", "运抵国", "随附单证及编号"
    ],
    15: [  # 提/运单
        "件数", "指运港", "提运单号", "毛重", "运抵国"
    ],
    19: [  # 空运运单
        "主运单号", "件数", "指运港", "毛重"
    ]
}

# 不同文件类型对应的表体字段（preDecList）
LIST_FIELDS_BY_TYPE = {
    1: [  # 合同
        "件数单项", "净重单项", "单价", "商品名称", "商品编号", "币制",
        "总价", "成交单位", "成交数量", "最终目的国", "毛重单项", "法定第一数量",
        "法定第二数量", "规格型号"
    ],
    2: [  # 发票
        "件数单项", "净重单项", "单价", "商品名称", "商品编号", "境内货源地",
        "币制", "总价", "成交单位", "成交数量", "最终目的国", "毛重单项",
        "法定第一数量", "法定第二数量", "规格型号"
    ],
    3: [  # 装箱单
        "件数单项", "净重单项", "商品名称", "商品编号", "境内货源地", "成交单位",
        "成交数量", "最终目的国", "毛重单项", "法定第一数量", "法定第二数量",
        "规格型号"
    ],
    4: [  # 预录入单
        "净重单项", "单价", "原产国", "商品名称", "商品编号", "境内货源地",
        "币制", "征免", "总价", "成交单位", "成交数量", "最终目的国", "毛重单项",
        "法定第一数量", "法定第二数量", "规格型号"
    ],
    5: [  # 申报要素
        "商品名称", "商品编号", "境内货源地", "规格型号"
    ],
    14: [  # 电子底账
        "商品名称", "商品编号", "币制", "总价", "最终目的国"
    ],
    15: [  # 提/运单
        "最终目的国"
    ],
    19: [  # 空运运单
        # 空运运单没有表体字段
    ]
}

def get_fields_for_type(att_type_code: int) -> tuple:
    """
    根据文件类型代码获取对应的表头和表体字段列表
    
    Args:
        att_type_code: 文件类型代码
        
    Returns:
        (head_fields, list_fields): 表头字段列表和表体字段列表
    """
    head_fields = HEAD_FIELDS_BY_TYPE.get(att_type_code, [])
    list_fields = LIST_FIELDS_BY_TYPE.get(att_type_code, [])
    return head_fields, list_fields


# 反向映射：每个key（英文字段名）对应的有效文件类型列表
KEY_TO_VALID_ATT_TYPES = {}

def _build_key_to_valid_att_types():
    """构建key到有效文件类型的映射"""
    global KEY_TO_VALID_ATT_TYPES
    KEY_TO_VALID_ATT_TYPES = {}
    
    # 遍历所有文件类型的表头字段
    for att_type, fields in HEAD_FIELDS_BY_TYPE.items():
        for field in fields:
            key = KEY_DESC_TO_KEY.get(field)
            if key:
                if key not in KEY_TO_VALID_ATT_TYPES:
                    KEY_TO_VALID_ATT_TYPES[key] = {'head': set(), 'list': set()}
                KEY_TO_VALID_ATT_TYPES[key]['head'].add(att_type)
    
    # 遍历所有文件类型的表体字段
    for att_type, fields in LIST_FIELDS_BY_TYPE.items():
        for field in fields:
            key = KEY_DESC_TO_KEY.get(field)
            if key:
                if key not in KEY_TO_VALID_ATT_TYPES:
                    KEY_TO_VALID_ATT_TYPES[key] = {'head': set(), 'list': set()}
                KEY_TO_VALID_ATT_TYPES[key]['list'].add(att_type)

# 初始化映射
_build_key_to_valid_att_types()


def is_valid_source(key: str, att_type_code: int, field_type: str) -> bool:
    """
    判断某个key从某个文件类型来源是否有效
    
    Args:
        key: 英文字段名
        att_type_code: 文件类型代码
        field_type: 字段类型，'head'或'list'
        
    Returns:
        是否为有效来源
    """
    if key not in KEY_TO_VALID_ATT_TYPES:
        return False
    return att_type_code in KEY_TO_VALID_ATT_TYPES[key].get(field_type, set())


def fuzzy_match_key_desc(key_desc: str) -> str:
    """
    模糊匹配字段名称，返回对应的英文key
    首先精确匹配，如果失败则尝试部分匹配
    
    Args:
        key_desc: 字段描述（中文名称）
        
    Returns:
        对应的英文key，如果未找到返回空字符串
    """
    # 首先尝试精确匹配
    if key_desc in KEY_DESC_TO_KEY:
        return KEY_DESC_TO_KEY[key_desc]
    
    # 去除空格和特殊字符后尝试匹配
    cleaned = key_desc.strip().replace(' ', '')
    for standard_name, key in KEY_DESC_TO_KEY.items():
        if cleaned == standard_name.replace(' ', ''):
            return key
    
    # 尝试部分匹配（包含关系）
    # 优先匹配更长的关键词
    sorted_keys = sorted(KEY_DESC_TO_KEY.keys(), key=len, reverse=True)
    for standard_name in sorted_keys:
        # 去除括号内容进行匹配
        clean_standard = standard_name.split('(')[0].strip()
        clean_input = key_desc.split('(')[0].strip()
        
        if clean_standard in clean_input or clean_input in clean_standard:
            return KEY_DESC_TO_KEY[standard_name]
    
    # 如果还是找不到，返回空字符串
    return ''
