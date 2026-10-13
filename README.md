# 投研纵览 · research_library

**投研纵览是一款本地文件检索软件：把散落在文件夹里的资料整理成可检索的知识库，再通过 MCP 接入 Claude Code、Codex、WorkBuddy 等 AI 工具。**

几份文件可以直接拖进聊天框；当资料积累到几十、上百份时，就很难一次性全部放进 prompt，也不方便每次手动翻找。投研纵览为这个痛点而生：读取你选定文件夹中的长文本、报告、演示文稿和表格，按需识别图片里的文字，建立索引，再根据问题找出相关内容，连同原文位置交给 AI 研究。

你可以用它检索内部纪要、访谈记录、研究报告，或其他自己认为有价值且有权使用的文件。下载向量模型后支持语义与混合检索，不必事先记住文件名或原文的确切用词；文件新增、修改或移除时，可按设置自动同步索引。AI 取回的是问题相关的片段和出处，省去逐份找文件、反复上传的步骤。

目前主要面向投研场景，也适合论文、工作文档和个人知识资料的检索。macOS 使用原生 SwiftUI，Windows 使用 WinUI 3，索引和检索运行在本机。欢迎在 [Issues](https://github.com/yzc021101/Research-Library/issues) 反馈问题、使用体验和功能建议；提交示例时请先移除敏感内容。

## 下载与安装

[下载发行版](https://github.com/yzc021101/Research-Library/releases)。Mac 版本适用于 Apple Silicon 与 macOS 14 及以上；Windows 版本适用于 Windows 11 x64，可在 Windows 11 ARM 的 x64 兼容环境运行。

- Mac：打开 DMG，把“投研纵览”拖到“应用程序”。
- Windows：解压整个 ZIP，运行 `research_library/ResearchLibrary.Windows.exe`，保留同目录所有文件。缺少 Microsoft Visual C++ 运行库时，App 会从微软官网下载、验证数字签名并打开安装程序，请自行确认微软许可与系统安装提示。
- 基础包含 Python 及基础解析依赖；Windows 还包含 .NET 和 WinUI 运行库，无需安装开发工具。
- 设置里的“运行环境与可选组件”可以下载 OCR 与旧版 Office 转换组件。显示下载大小和进度，校验通过后安装；可取消或重试。安装或移除后重启服务。
- 向量模型独立按需下载。未下载模型时可使用关键词检索。

发行版使用本地签名，未购买 Apple Developer ID 公证或 Windows 商业代码签名。请核对官方仓库来源及 SHA256SUMS，通过系统正常安全提示允许运行，勿关闭系统安全保护。

## 检查更新

在“设置 → 软件更新”中检查 GitHub 正式发行版，选择下载，再点击“安装并重启”。更新只替换应用程序，保留资料库、模型、来源文件夹和 MCP 配置。安装包先校验 GitHub 提供的 SHA-256，完整准备后才替换旧版；替换失败会保留或恢复旧版。

可选“自动更新”默认关闭。开启后，App 运行时每天检查并下载一次更新，下载完成后仍由你选择安装并重启。更新检查只访问本项目 GitHub Release，不上传资料内容。请保留至少 5 GB 空闲空间，使用可写的安装目录；Mac 请先将 App 移出 DMG。Windows 如被仍在运行的 MCP 客户端占用，请关闭连接后重试。

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
