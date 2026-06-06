# MinerU PDF Analysis Skill

一个用于 Agent 的 PDF 分析 Skill。它通过 MinerU 的 OCR 与版面解析能力处理 PDF，生成原始 Markdown、清洗后的 Markdown 和元数据，方便 Agent 基于文档内容进行总结、问答、对比和信息抽取。相比传统 PDF 库，它对 PDF 文本层和版式规范的依赖更低，更适合扫描件、复杂排版、表格、公式等场景，解析结果也更稳定精准。

## 功能

- 上传 PDF 到 MinerU 并等待解析完成
- 支持 OCR 解析，对扫描版 PDF 和图片型页面更友好
- 相比传统 PDF 文本提取库，对格式要求更宽松
- 下载 MinerU 返回的解析结果
- 提取 `full.md` 作为原始 Markdown
- 生成空白规范化后的 cleaned Markdown
- 输出 `metadata.json`，记录 PDF 路径、输出路径、批次 ID 和解析参数
- 使用较短的输出目录和文件名，降低 Windows 路径过长风险

## 目录结构

```text
mineru-pdf-analysis/
├── SKILL.md
├── README.md
└── scripts/
    └── analyze_pdf_with_mineru.py
```

## 环境要求

- Python 3.10+
- 可访问 MinerU API
- MinerU API Token

脚本只使用 Python 标准库，不需要额外安装第三方依赖。

## 配置 Token

先前往 MinerU API 管理页面申请 Token：

https://mineru.net/apiManage/docs

拿到 Token 后，有三种方式可以配置 MinerU Token。

方式一：直接修改脚本里的默认 Token：

```python
DEFAULT_MINERU_TOKEN = "your token"
```

如果仓库会公开到 GitHub，不建议提交真实 Token。可以保留占位值，在本地使用环境变量或命令行参数覆盖。

方式二：通过环境变量配置。

PowerShell:

```powershell
$env:MINERU_TOKEN="your-mineru-token"
```

macOS / Linux:

```bash
export MINERU_TOKEN="your-mineru-token"
```

方式三：运行脚本时临时传入：

```bash
python scripts/analyze_pdf_with_mineru.py /path/to/file.pdf --token your-mineru-token
```

## 使用方式

在仓库根目录运行：

```bash
python scripts/analyze_pdf_with_mineru.py /path/to/file.pdf
```

Windows PowerShell 示例：

```powershell
python .\scripts\analyze_pdf_with_mineru.py "C:\Users\PC\Documents\example.pdf"
```

指定输出目录：

```bash
python scripts/analyze_pdf_with_mineru.py /path/to/file.pdf --output-dir ./mineru-output/example
```

扫描版 PDF 可开启 OCR：

```bash
python scripts/analyze_pdf_with_mineru.py /path/to/file.pdf --ocr
```

## 常用参数

- `--output-dir`: 指定 Markdown 和元数据输出目录
- `--token`: 临时覆盖 MinerU Token
- `--model-version`: MinerU 模型版本，默认 `vlm`
- `--language`: 文档语言，默认 `ch`
- `--ocr`: 启用 OCR，适合扫描版 PDF
- `--disable-table`: 关闭表格提取
- `--disable-formula`: 关闭公式提取
- `--timeout-seconds`: 轮询超时时间，默认 `3600`
- `--interval-seconds`: 轮询间隔，默认 `5`

## 输出结果

脚本成功后会在 stdout 打印 JSON，例如：

```json
{
  "pdf_path": "/absolute/path/to/file.pdf",
  "output_dir": "/absolute/path/to/mineru-output/1a2b3c4d",
  "raw_markdown_path": "/absolute/path/to/mineru-output/1a2b3c4d/<batch_id>.md",
  "cleaned_markdown_path": "/absolute/path/to/mineru-output/1a2b3c4d/<batch_id>.cleaned.md",
  "metadata_path": "/absolute/path/to/mineru-output/1a2b3c4d/metadata.json",
  "batch_id": "mineru-batch-id",
  "model_version": "vlm",
  "language": "ch",
  "enable_table": true,
  "enable_formula": true,
  "is_ocr": false,
  "pdf_size": 12345
}
```

输出目录中通常包含：

- `<batch_id>.md`: MinerU 原始 Markdown
- `<batch_id>.cleaned.md`: 清洗后的 Markdown，推荐给 Agent 做文档问答
- `metadata.json`: 本次解析的元数据

## Agent 使用建议

当用户上传或引用 PDF 时，Agent 应先运行：

```bash
python skills/mineru-pdf-analysis/scripts/analyze_pdf_with_mineru.py /path/to/user-uploaded.pdf
```

然后读取 stdout JSON 里的 `cleaned_markdown_path`，基于清洗后的 Markdown 回答用户问题。只有在需要核对 MinerU 原始输出时，才读取 `raw_markdown_path`。

## 清洗规则

cleaned Markdown 的处理保持保守，只做基础格式规范化：

- 移除非空行末尾空白
- 合并连续空行
- 移除文档首尾空行

不会删除领域内容、页眉页脚、表格、公式或正文段落。

## 常见问题

### Missing MinerU token

说明没有配置 MinerU Token。请设置 `MINERU_TOKEN`，或使用 `--token` 参数。

### MinerU extraction failed

MinerU 解析失败。可以查看错误信息；如果是扫描版 PDF，建议加上 `--ocr` 后重试。

### Polling timed out

解析超时。大文件或复杂 PDF 可以提高 `--timeout-seconds`。

### Could not find full.md

MinerU 返回的 zip 中没有 `full.md`，说明本次解析结果不完整或格式异常。

## License

按你的仓库 License 使用。若准备开源，建议补充 `LICENSE` 文件。
