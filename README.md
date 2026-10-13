# 投研纵览 · research_library

本地资料库与 MCP 服务。macOS 使用 SwiftUI，Windows 使用 WinUI 3；资料索引和检索保存在你的电脑上。

## 下载与安装

[下载发行版](https://github.com/yzc021101/Research-Library/releases)。Mac 版本适用于 Apple Silicon 与 macOS 14 及以上；Windows 版本适用于 Windows 11 x64，可在 Windows 11 ARM 的 x64 兼容环境运行。

- Mac：打开 DMG，把“投研纵览”拖到“应用程序”。
- Windows：解压整个 ZIP，运行 `research_library/ResearchLibrary.Windows.exe`，保留同目录所有文件。缺少 Microsoft Visual C++ 运行库时，App 会从微软官网下载、验证数字签名并打开安装程序，请自行确认微软许可与系统安装提示。
- 基础包含 Python 及基础解析依赖；Windows 还包含 .NET 和 WinUI 运行库，无需安装开发工具。
- 设置里的“运行环境与可选组件”可以下载 OCR 与旧版 Office 转换组件。显示下载大小和进度，校验通过后安装；可取消或重试。安装或移除后重启服务。
- 向量模型独立按需下载。未下载模型时可使用关键词检索。

发行版使用本地签名，未购买 Apple Developer ID 公证或 Windows 商业代码签名。请核对官方仓库来源及 SHA256SUMS，通过系统正常安全提示允许运行，勿关闭系统安全保护。

## 支持的资料

PDF、DOCX、PPTX、XLSX、Markdown、TXT、RTF、CSV、TSV。DOC/PPT/XLS 通过可选 LibreOffice 组件转换；扫描 PDF 和 Office 内嵌图片通过可选 Tesseract OCR 识别。表格公式读取缓存值，不重新计算；OCR 和旧版格式转换的关键数字应回看原件。

默认关联来源文件，不复制原文。自动同步按设置检测新增、修改和移除的文件。原文快照为可选项，可在设置中清理。

## MCP 接入

首次启动向导选择资料文件夹，再在“MCP 接入”选择客户端并复制配置。支持本地 STDIO 的 Codex、WorkBuddy、Claude Code、Cursor、VS Code 等工具。本地接入不需要远程 URL 或 MCP Key。移动 App 后重新复制配置。在客户端调用 `library_status` 验证连接。

## 隐私

默认不上传用户资料。索引、设置、日志、缓存与可选组件集中保存在 Mac 的 `~/Library/Application Support/research_library` 或 Windows 的 `%LOCALAPPDATA%\research_library`。下载组件、模型及打开帮助链接会访问对应发布站点。通过 MCP 交给 AI 客户端的原文片段会进入该客户端的对话环境，请按自己的资料授权范围使用。

安装包不含开发者资料、索引、账号配置或模型缓存。初次运行创建个人资料目录。卸载可删除 App 和自己的上述资料目录；来源文件不受影响。

## 开源与构建

原始项目采用 **AGPL-3.0-only**（自有前端附带 [平台链接额外许可](PLATFORM-LINKING-PERMISSION.txt)），见 [LICENSE](LICENSE)。[BUILDING.md](BUILDING.md) 说明构建步骤。发行标签中的代码对应同版本二进制；依赖许可、源码获取方式及可选组件修改见 `THIRD_PARTY_NOTICES`。重分发须继续满足相应许可证。

本软件由社区维护，以现状提供，不附带担保。第三方工具名称仅用于说明互操作性，不表示隶属或背书。
