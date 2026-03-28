# Book2MD

书籍批量转换 Markdown 工具。上传 PDF、EPUB、MOBI、AZW3 等格式电子书，一键转换为 Markdown。

## 功能

- **多格式支持**：PDF、EPUB、MOBI、AZW、AZW3、KFX、DJVU、FB2、CBZ、CBR
- **影印版 PDF 识别**：自动检测扫描页，OCR 提取中英文内容
- **智能排版**：自动识别标题层级、加粗等格式
- **批量转换**：支持多文件同时上传转换
- **实时进度**：逐页显示转换进度
- **在线预览**：转换完成后可直接在浏览器预览 Markdown 渲染效果
- **灵活下载**：单个下载或全部打包 ZIP 下载
- **转换历史**：查看所有已转换书籍

## 快速开始

### 环境要求

- Python 3.9+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)（影印版 PDF 需要）
- [Calibre](https://calibre-ebook.com/)（MOBI/AZW3 等格式需要）

### macOS 安装依赖

```bash
brew install tesseract tesseract-lang calibre
```

### 启动服务

```bash
cd book2md
pip install -r requirements.txt
python app.py
```

打开浏览器访问 **http://localhost:8090**

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| PDF 提取 | PyMuPDF |
| PDF OCR | PyMuPDF + Tesseract |
| EPUB 转换 | ebooklib + html2text |
| MOBI/AZW3 | Calibre ebook-convert → EPUB → MD |
| 前端预览 | marked.js |

## 项目结构

```
book2md/
├── app.py              # FastAPI 主应用
├── converter.py        # 转换核心逻辑
├── templates/
│   └── index.html      # 前端页面
├── requirements.txt    # Python 依赖
└── uploads/            # 临时文件（自动创建）
```

## License

MIT
