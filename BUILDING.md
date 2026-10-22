# 从对应源码构建

本标签包含实际应用代码、图标源文件、两端前端、完整后端和构建脚本。未对 PyMuPDF/MuPDF 源码作修改。发行包的第三方二进制取自其官方发行物；版本、许可证及源码见 THIRD_PARTY_NOTICES。源代码链接也可在 App 设置和 MCP 的 library_status 中找到。

## macOS ARM64

需要 macOS 14+、Apple Command Line Tools（Swift 编译器、iconutil、codesign、hdiutil）及独立安装的标准 CPython 3.12 ARM64（本版本使用 3.12.13）。请使用 Python 或 python-build-standalone 的公开发行物，避免复用其他工具定制的解释器。创建项目自己的虚拟环境并安装锁定依赖：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt -r packaging/requirements-build.txt
sh packaging/build-macos.sh
```

输出 dist/research_library-macos-arm64.dmg。当前为 ad-hoc 本地签名；重建不需要发布者私钥。图标可通过 native/build-icon.sh 从随附 PNG 重新导出。

## Windows x64

需要 Inno Setup 6.7.3（ISCC.exe 可用）、Windows 11、CPython 3.12 x64、.NET 10 SDK、对应 Windows SDK/WinUI 编译工具。恢复依赖后在 PowerShell 调用：

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r windows/requirements-windows.lock.txt -r packaging/requirements-build.txt
./packaging/build-windows.ps1 -Python .venv/Scripts/python.exe -DotNet dotnet
```

输出 dist/research_library-windows-x64-setup.exe（安装向导）及 dist/research_library-windows-x64.zip（供内置更新器及便携使用）。安装器默认在当前用户目录安装，不要求管理员权限；应用文件在 app 子目录中，卸载程序与该目录并列，避免应用自动更新时替换卸载记录。用户资料存放在独立资料库目录，卸载保留资料。PowerShell 执行策略由构建者按其环境管理；脚本不修改系统策略。优先在 x64 Windows 构建。runtime.spec 排除独立 VC CRT DLL，再由 App 引导用户从微软官网下载运行库；inspect-pe.py 拒绝不兼容架构。源码中的 windows_runtime.py 为用户已安装的系统运行库生成必要的 DLL 文件名别名。

## 可选组件与下载清单

packaging/components-<platform>.json 固定每个组件 ZIP 的 URL、大小、SHA-256 和启动文件。先用 pack_component.py 打包有合法再分发许可的载荷，再用 configure_online_release.py 生成同一不可变版本标签的清单；更改组件后必须重新构建 App。组件里的 THIRD_PARTY_NOTICES/SOURCES 文档说明二进制来源、所作修改及对应源码。模型不打入安装包。

## 测试

```sh
.venv/bin/python packaging/verify_release.py <engine> build/package-core-test build/core-checks.json
.venv/bin/python tests/test_online_components.py
```

核心检查创建九种合成文件，验证关键词检索、原文回读、MCP 握手、修改与删除。第二项启动本机 TLS 测试服务器，验证下载、取消、重试、完整性和路径安全；需要本机回环监听权限及 openssl。发布后还须用最终清单从公开 Release 实际下载、安装与运行组件。

开发启动：从 src/backend.py 或 windows/backend/backend.py 启动服务。通过 RESEARCH_LIBRARY_ROOT 指定隔离资料目录；Windows 源码前端另需显式指定 RESEARCH_LIBRARY_DEV_ROOT 为后端与 .venv 所在目录。发行版始终使用捆绑引擎。
