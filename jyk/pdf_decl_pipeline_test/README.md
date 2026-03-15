# pdf_decl_pipeline_test

PDF 源坐标交叉验证小测验：

- 按页渲染 PDF 图片（每页限制到 `4096x4096` 以内）
- 提取 PDF words 级别源坐标（PyMuPDF）
- 调用 Qwen3-VL 识别字段
- 用 PDF 源文本与 bbox 做交叉验证和坐标纠偏
- 输出 OCR 兼容 JSON（含 `matchLevel/coordCorrected/pdfPage/sourceType`）

## 运行

```bash
python -m jyk.pdf_decl_pipeline_test.main \
  --pdf_path d:/code/YiBao/jyk/transition/files/pdf/RELNBI09149报关.pdf \
  --att_type_code 4 \
  --output_json d:/code/YiBao/jyk/pdf_decl_pipeline_test/output.json
```

## 依赖

```bash
pip install -r jyk/pdf_decl_pipeline_test/requirements.txt
```

