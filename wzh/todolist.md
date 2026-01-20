# 待办清单（性能优化）

1. 为图片识别调用增加并发上限（`asyncio.Semaphore`），避免 API 过载并提升整体吞吐。（`归档/customs_ocr/core/ocr_service.py`）
2. 将“图片预处理（下载 + OSD）”与“VLM 调用”做成流水线，并分别设置并发上限。（`归档/customs_ocr/main.py`）
3. 批量运行脚本改为并行执行（多进程或异步 + 限流），加速离线处理。（`归档/customs_ocr/run_multiple_times.py`）
4. <span style="color:red">[已完成]</span> 复用 `AsyncOpenAI` 客户端实例，减少连接/握手开销。（`归档/customs_ocr/core/ocr_service.py`）
5. 复用 `requests.Session()` 并加入 URL→base64 缓存，减少重复下载。（`归档/customs_ocr/core/image_preprocessor.py`）
6. <span style="color:red">[已完成]</span> 只加载一次 tokenizer / model，并按 `convert_class` 缓存 embeddings。（`归档/customs_ocr/core/post_processor.py`）
7. 避免 `transform_source_list` 重复调用，减少冗余开销。（`归档/customs_ocr/core/post_processor.py`）
8. 一致性校验前做本地规范化 + 结果缓存，减少 LLM 调用次数。（`归档/customs_ocr/core/aggregator.py`）
9. 过滤 `is_mainfactor=True` 时的异常结果，避免异常被当作有效结果。（`归档/customs_ocr/core/ocr_service.py`）
10. `get_mainfactor` 避免重复调用 `reback(hsCode)`，并增加 HS→mainfactor 缓存。（`归档/customs_ocr/core/mainfactor_utils.py`）
11. 增加 OSD 跳过策略（EXIF/尺寸/置信度），降低 CPU 开销。（`归档/customs_ocr/core/image_preprocessor.py`）
12. 如 API 支持，优先传 URL，必要时才 base64；并加磁盘缓存兜底。（`归档/customs_ocr/core/image_preprocessor.py`）
