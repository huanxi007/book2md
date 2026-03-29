# Book2MD

书籍 & 笔记批量转换 Markdown 工具。支持电子书、扫描件、印象笔记等多种格式，拖拽上传，一键转换。

## 支持格式

| 格式 | 说明 |
|------|------|
| PDF | 普通 PDF 直接提取；影印版/扫描版自动 OCR（中英文） |
| EPUB | 电子书标准格式 |
| MOBI / AZW / AZW3 / KFX | Kindle 电子书格式 |
| **印象笔记 .notes** | **自动解密加密导出文件**，通过 API 获取原文转换 |
| **印象笔记 .enex** | Evernote 标准导出格式，直接转换 |
| XML | 结构化 XML 或 HTML-like XML |
| DJVU / FB2 / CBZ / CBR | 其他电子书 & 漫画格式 |

## 功能亮点

- **印象笔记破解**：新版印象笔记导出的 `.notes` 文件内容是 AES 加密的，本工具自动从 macOS 钥匙串获取 token，通过印象笔记 API 拿到明文并转换
- **影印版 PDF 识别**：逐页检测，有文字层的快速提取，扫描页自动 OCR
- **智能排版**：根据字体大小自动识别标题层级（H1/H2/H3）和加粗
- **批量转换**：拖拽多文件上传，并发转换，实时显示逐页进度
- **在线预览**：转换完成后直接在浏览器预览 Markdown 渲染效果
- **灵活下载**：单个下载或全部打包 ZIP 下载
- **转换历史**：查看所有已完成转换，随时预览和下载
- **失败详情**：转换失败时显示具体错误原因

## 快速开始

### 环境要求

- Python 3.9+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)（影印版 PDF 需要）
- [Calibre](https://calibre-ebook.com/)（MOBI/AZW3 等格式需要）
- 印象笔记 Mac 客户端已登录（解密 `.notes` 文件需要）

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
| 印象笔记 | Evernote SDK + macOS Keychain |
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
