# excel_decl_pipeline

报关单 Excel 处理流水线，支持：

- 读取 `.xls/.xlsx` 并自动裁剪有效区域
- AutoFit 渲染，保证单元格内容完整显示
- 超过 `max_side` 时按行/列边界分图
- 使用 Qwen3-VL 对分图识别字段
- 结合 Excel 原始单元格做字段比对与坐标纠偏
- 输出 OCR 兼容 JSON

运行方式：

```bash
python -m jyk.excel_decl_pipeline.main \
  --excel_path <input.xlsx> \
  --att_type_code 4 \
  --output_json <output.json>
```

