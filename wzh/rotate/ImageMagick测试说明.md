# ImageMagick 精调测试说明

## 安装步骤

### 1. 安装 ImageMagick（必须！）

**Windows 系统：**

1. 下载 ImageMagick：https://imagemagick.org/script/download.php
2. 选择 Windows Binary Release
3. 下载 `ImageMagick-7.x.x-Q16-HDRI-x64-dll.exe`
4. 安装时**务必勾选**：
   - ✅ Install legacy utilities (e.g., convert)
   - ✅ Add application directory to your system path

5. 安装完成后，验证：
   ```bash
   magick --version
   ```

### 2. Python 库已安装

✅ Wand 库已安装（ImageMagick 的 Python 接口）

## 运行测试

```bash
python c:\desktop\YiBao\wzh\rotate\test_accuracy_imagemagick.py
```

## 核心区别

### 原始脚本 (`test_accuracy.py`)
- **粗调**：Tesseract OSD
- **精调**：OpenCV 形态学 + 轮廓检测

### ImageMagick 脚本 (`test_accuracy_imagemagick.py`)
- **粗调**：Tesseract OSD（相同）
- **精调**：ImageMagick deskew

## ImageMagick deskew 工作原理

```
1. 输入：已经粗调过的图片（基本正向，可能有微小倾斜）
2. deskew 处理：
   - 分析图片中的文本行
   - 使用霍夫变换检测直线
   - 计算平均倾斜角度
   - 自动旋转矫正
3. 输出：矫正后的图片
```

**注意**：ImageMagick 不直接返回检测到的角度，所以脚本使用了一个间接方法：
- 用 deskew 矫正图片
- 用 OpenCV 检测矫正后的残余倾斜
- 反推原始倾斜角度

## 预期效果对比

| 方法 | 优势 | 劣势 |
|------|------|------|
| **OpenCV** | 可自定义参数，更灵活 | 需要手动调优参数 |
| **ImageMagick** | 算法成熟，自动化程度高 | 不返回角度值，需要间接推算 |

## 输出文件

测试结果保存在 `test_results_imagemagick/` 目录：
- `coarse_accuracy_results_imagemagick.json` - 粗调详细结果
- `fine_accuracy_results_imagemagick.json` - 精调详细结果
- `summary_imagemagick.json` - 汇总报告
- `coarse_errors/` - 粗调错误的图片
- `fine_errors_imagemagick/` - 精调错误的图片

## 对比建议

运行两个脚本后，对比：
1. **精调准确率**
2. **平均误差**
3. **中位数误差**
4. **错误图片类型**

看哪种方法更适合你的场景！
