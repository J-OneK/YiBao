# 报关文档识别系统

基于视觉大语言模型的报关文档字段自动识别系统，支持异步并发处理。

## 项目结构

```
customs_ocr/
├── config/                  # 配置模块
│   ├── __init__.py
│   ├── settings.py         # 全局配置（API密钥、模型配置等）
│   └── field_mapping.py    # 字段映射配置（支持模糊匹配和来源验证）
├── core/                    # 核心模块
│   ├── __init__.py
│   ├── models.py           # 数据模型定义
│   ├── data_loader.py      # 数据加载器
│   ├── prompt_manager.py   # Prompt模板管理
│   ├── ocr_service.py      # OCR服务（支持异步并发）
│   ├── json_utils.py       # JSON解析和验证工具
│   ├── aggregator.py       # 结果聚合（支持异步并发）
│   └── post_processor.py   # 后处理（坐标转换等）
├── main.py                  # 主程序入口（异步）
├── requirements.txt         # Python依赖库
└── README.md               # 本文件
```

## 核心功能

### 1. 异步并发处理
- **图片识别并发**：所有图片同时发送给大模型识别，大幅提升速度
- **值一致性判断并发**：所有字段的值一致性判断并发执行
- **性能提升**：相比串行处理，速度提升10-50倍（取决于图片和字段数量）

### 2. 智能字段识别
- **多文件类型支持**：支持8种文件类型（合同、发票、装箱单等）
- **字段模糊匹配**：自动识别字段名称的各种变体（带空格、括号等）
- **来源验证**：严格按照Excel定义验证字段来源，确保数据准确性

### 3. 智能值一致性处理
- **数值智能比较**：对纯数值字段，先转换为数字比较，避免不必要的大模型调用
  - `"789.90"` 和 `"789.9"` 会被识别为相同值
- **语义判断**：对非数值字段，使用 qwen-flash 模型判断语义是否相同
  - `"USA"` 和 `"美国"` 会被识别为相同含义
  - `"montreal"` 和 `"蒙特利尔"` 会被识别为相同含义

### 4. 完整的数据处理流程
1. 从JSON文件加载图片信息
2. 并发调用视觉模型识别所有图片
3. 实时进行字段映射和来源验证
4. 按keyDesc聚合多图片结果
5. 并发检查值一致性并统一
6. 坐标转换和最终格式化
7. 输出结构化JSON结果

## 安装

### 1. 安装Python依赖

```bash
cd customs_ocr
pip install -r requirements.txt
```

### 2. 配置API密钥（可选）

创建 `.env` 文件或设置环境变量：
```
API_KEY=your-api-key-here
```

如果不设置，将使用默认的API密钥。

## 使用方法

### 基本用法

```bash
python main.py
```

默认读取 `../OCR识别报文.json`，输出到 `./output_result.json`。

### 指定文件路径

```bash
python main.py <输入JSON路径> <输出JSON路径>
```

例如：
```bash
python main.py /path/to/input.json /path/to/output.json
```

## 输出格式

```json
{
  "preDecHead": [
    {
      "keyDesc": "境内收发货人名称",
      "key": "consigneeCname",
      "parsedValue": "福州大康机械设备有限公司",
      "sourceList": [
        {
          "value": "福州大康机械设备有限公司",
          "startx": 157,
          "starty": 303,
          "endx": 463,
          "endy": 321,
          "imageId": "5"
        }
      ]
    }
  ],
  "preDecList": [
    [
      {
        "keyDesc": "商品名称",
        "key": "gName",
        "parsedValue": "输送机零件导向轮",
        "sourceList": [
          {
            "value": "输送机零件导向轮",
            "startx": 157,
            "starty": 836,
            "endx": 778,
            "endy": 854,
            "imageId": "5"
          }
        ]
      }
    ]
  ]
}
```

## 支持的文件类型

| 代码 | 类型 | 表头字段数 | 表体字段数 |
|-----|------|-----------|-----------|
| 1 | 合同 | 23 | 15 |
| 2 | 发票 | 23 | 16 |
| 3 | 装箱单 | 15 | 13 |
| 4 | 预录入单 | 36 | 17 |
| 5 | 申报要素 | 1 | 5 |
| 14 | 电子底账 | 5 | 5 |
| 15 | 提/运单 | 5 | 1 |
| 19 | 空运运单 | 4 | 0 |

## 技术架构

### 双模型策略
- **qwen3-vl-flash**：图片字段识别（视觉模型）
- **qwen-flash**：文本语义判断（快速文本模型）

### 异步并发
- 使用 Python asyncio 实现异步处理
- 使用 AsyncOpenAI 客户端进行并发API调用
- 使用 `asyncio.gather()` 并发执行多个任务

### 数据验证
- **字段映射**：支持精确匹配、去空格匹配、部分匹配三级策略
- **来源验证**：根据Excel定义验证每个字段的有效来源
- **自动过滤**：过滤掉无效字段和无效来源

### 容错机制
- JSON解析失败自动重试，最多3次
- 自动去除markdown标记
- 异常处理确保部分失败不影响整体

## 配置说明

### config/settings.py

```python
API_KEY = "your-api-key"              # API密钥
API_BASE_URL = "..."                  # API基础URL
MODEL_NAME = "qwen3-vl-flash"        # 视觉模型
TEXT_MODEL_NAME = "qwen-flash"       # 文本模型
MAX_RETRIES = 3                       # 最大重试次数
LOG_LEVEL = "INFO"                    # 日志级别
```

### config/field_mapping.py

包含：
- `ATT_TYPE_NAMES`: 文件类型映射
- `KEY_DESC_TO_KEY`: 中英文字段映射（100+字段）
- `HEAD_FIELDS_BY_TYPE`: 各文件类型的表头字段定义
- `LIST_FIELDS_BY_TYPE`: 各文件类型的表体字段定义
- `fuzzy_match_key_desc()`: 模糊匹配函数
- `is_valid_source()`: 来源验证函数

## 处理逻辑详解

### 阶段1：图片识别（并发）
```
输入图片 → 生成Prompt → 并发调用API → JSON解析 → 字段映射 → 来源验证 → 过滤无效字段
```

### 阶段2：结果聚合
```
按keyDesc分组 → 合并sourceList → 补充英文key
```

### 阶段3：值一致性处理（并发）
```
检测值差异 → 数值比较 / 大模型判断（并发） → 统一value
```

### 阶段4：后处理
```
生成parsedValue → 坐标转换[0-999]→实际像素 → 输出JSON
```

## 日志示例

```
2025-12-17 11:00:00 - __main__ - INFO - 报关文档识别系统启动（异步并发模式）
2025-12-17 11:00:00 - __main__ - INFO - 步骤 1/5: 加载输入数据...
2025-12-17 11:00:00 - __main__ - INFO - 成功加载 5 张图片信息
2025-12-17 11:00:00 - __main__ - INFO - 步骤 2/5: 并发调用视觉大模型识别图片...
2025-12-17 11:00:05 - __main__ - INFO - 成功识别 5/5 张图片
2025-12-17 11:00:05 - __main__ - INFO - 步骤 3/5: 聚合多图片识别结果...
2025-12-17 11:00:05 - __main__ - INFO - 步骤 4/5: 并发检查字段一致性...
2025-12-17 11:00:08 - __main__ - INFO - 步骤 5/5: 后处理...
2025-12-17 11:00:08 - __main__ - INFO - 报关文档识别系统完成
```

## 注意事项

1. **API配额**：并发调用可能快速消耗API配额
2. **网络要求**：确保网络能访问图片URL和API地址
3. **并发控制**：如需限制并发数，可在代码中添加信号量控制
4. **内存占用**：并发处理会占用更多内存

## 故障排查

### 识别失败
1. 检查图片URL是否可访问
2. 检查API密钥是否正确
3. 查看详细日志信息

### JSON解析失败
1. 系统会自动重试3次
2. 检查模型返回内容（DEBUG日志级别）
3. 可能需要调整prompt模板

### 字段被过滤
1. 检查字段名称是否在映射表中
2. 检查字段来源是否符合Excel定义
3. 查看WARNING级别日志

## 扩展开发

### 添加新字段
在 `config/field_mapping.py` 中添加：
```python
KEY_DESC_TO_KEY["新字段"] = "newKey"
HEAD_FIELDS_BY_TYPE[file_type].append("新字段")
```

### 调整并发数量
在 `core/ocr_service.py` 中使用信号量控制：
```python
semaphore = asyncio.Semaphore(10)  # 最多10个并发
```

### 自定义一致性判断规则
修改 `core/aggregator.py` 中的判断逻辑。
