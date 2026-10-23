import SwiftUI
import AppKit

struct OnboardingView: View {
    @ObservedObject var m: LibraryModel
    var finish: (Bool) -> Void
    @State private var step = 0
    private let titles = ["选择模型与 OCR", "准备资料库", "连接你的 AI 工具", "验证连接"]
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 16) {
                Image(nsImage: NSApp.applicationIconImage).resizable().frame(width: 64, height: 64)
                VStack(alignment: .leading, spacing: 6) {
                    Text("接入 投研纵览").font(.title2.weight(.semibold))
                    Text("第 \(step + 1) 步，共 4 步 · \(titles[step])").foregroundStyle(.secondary)
                }
                Spacer()
            }.padding(24)
            Divider()
            Form {
                if step == 0 {
                    OnboardingComponents(m: m)
                } else if step == 1 {
                    Section {
                        LabeledContent("资料来源", value: "\(m.preferences.sourceFolders.count) 个文件夹")
                        HStack { Spacer(); Button("添加资料文件夹…") { m.addFolder() } }
                    } header: {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("欢迎使用").font(.headline).foregroundStyle(.primary)
                            FormNote("让你的 AI 工具检索本机报告、Word、PPT、表格和文本，并取回原文及出处。\n接下来会生成适合你所用客户端的配置，再检查本地 MCP 是否可以连接。")
                            Text("准备资料").font(.headline).foregroundStyle(.primary).padding(.top, 18)
                        }
                    } footer: {
                        FormNote("可以稍后添加。来源文件只读，索引和模型保存在资料库目录中。")
                    }
                    Section {
                        HStack {
                            LabeledContent("服务状态", value: m.stateLabel)
                            if !m.running { Button("启动服务") { Task { await m.start() } }.disabled(m.starting) }
                        }
                    } header: { Text("连接准备") } footer: {
                        VStack(alignment: .leading, spacing: 6) {
                            FormNote("客户端通过本地启动命令接入，无需填写 URL 或密钥。")
                            FormNote("经 MCP 提供给 AI 客户端的原文片段会进入它的对话上下文。")
                        }
                    }
                } else if step == 2 {
                    MCPClientSections(root: m.root)
                } else {
                    MCPStatusSection(m: m, showClientReminder: true)
                    Section {
                        HStack {
                            Text("在客户端验证连接")
                            Spacer()
                            Button("复制验证提示词") {
                                NSPasteboard.general.clearContents()
                                NSPasteboard.general.setString(MCPClient.verificationPrompt, forType: .string)
                            }
                        }
                    } header: { Text("在客户端中验证") } footer: {
                        VStack(alignment: .leading, spacing: 8) {
                            FormNote("返回你使用的 AI 客户端，确认服务器已经启用，然后发送以下提示词：")
                            Text(MCPClient.verificationPrompt)
                                .font(.system(.body, design: .monospaced)).foregroundStyle(.primary)
                                .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                                .frame(maxWidth: .infinity, alignment: .leading).padding(12)
                                .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Color(nsColor: .separatorColor)))
                                .accessibilityIdentifier("VerificationPrompt")
                            FormNote("客户端能调用 library_status 后即可开始使用。文档数为 0 时，可以先添加资料来源。")
                            Text("日常使用").font(.headline).foregroundStyle(.primary).padding(.top, 18)
                            FormNote("关闭所有窗口后可继续留在菜单栏运行；从菜单栏重新打开窗口。需要释放资源时选择“停止服务”。")
                        }
                    }

                }
                if let message = m.message { Section { } footer: { FormNote(message) } }
            }.formStyle(.grouped)
            Divider()
            HStack {
                Button("稍后配置") { finish(false) }
                Spacer()
                if step > 0 { Button("上一步") { step -= 1 } }
                Button(step == 3 ? "完成引导" : "下一步") {
                    if step < 3 { step += 1 } else { finish(true) }
                }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
            }.padding(20)
        }.frame(width: 720, height: 680)
    }
}

struct OnboardingComponents: View {
    @ObservedObject var m: LibraryModel
    @State private var selected = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    var option: ModelOption? { m.models.first { $0.id == selected } }
    var ocr: [String: Any] { (m.componentInfo["items"] as? [[String: Any]] ?? []).first { $0["id"] as? String == "ocr" } ?? [:] }
    var job: [String: Any] { m.componentInfo["job"] as? [String: Any] ?? [:] }
    var working: Bool { m.busy || m.modelBusy || ["downloading", "installing"].contains(job["phase"] as? String ?? "") }
    var body: some View {
        Section {
            Picker("向量模型", selection: $selected) {
                ForEach(m.models) { item in Text(item.name + (item.id.contains("MiniLM") ? "（推荐）" : "")).tag(item.id) }
            }
            HStack {
                Text(option?.downloaded == true ? "已安装，无需重复下载" : String(format: "预计下载 %.2f GB · 请预留至少 %.2f GB 空间", option?.downloadGB ?? 0.22, (option?.downloadGB ?? 0.22) * 2))
                    .font(.callout).foregroundStyle(.secondary)
                Spacer()
                Button(option?.downloaded == true ? "已安装" : "下载并安装模型") { Task { await m.switchModel(selected) } }
                    .disabled(working || !m.running || option?.downloaded == true)
            }
            if m.modelBusy {
                ProgressView(m.modelJob["phase"] as? String == "indexing" ? "正在建立向量索引…" : "正在下载并准备模型…")
                HStack { Spacer(); Button("取消模型任务") { Task { await m.cancelModel() } } }
            }
            if let error = m.modelJob["error"] as? String, !error.isEmpty { FormNote(error + " 可点击下载按钮重试。") }
        } header: { Text("向量模型 · 推荐 MiniLM") } footer: {
            FormNote("用于按语义检索本地资料。MiniLM 较轻量，支持中文和多语言；可以稍后安装，暂时使用关键词检索。")
        }
        Section {
            HStack {
                VStack(alignment: .leading, spacing: 6) {
                    Text("图片文字识别（OCR）")
                    Text((ocr["installed"] as? Bool == true || ocr["external"] as? Bool == true) ? "已就绪，无需重复安装" : "下载 " + size(ocr["download_bytes"]) + " · 安装后 " + size(ocr["expanded_bytes"]))
                        .font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                Button("下载并安装 OCR") { Task { do { _ = try await m.post("/components/install", ["id": "ocr"]); await m.refresh() } catch { m.message = error.localizedDescription } } }
                    .disabled(working || !m.running || ocr["url"] == nil || ocr["installed"] as? Bool == true || ocr["external"] as? Bool == true)
            }
            if ["downloading", "installing"].contains(job["phase"] as? String ?? "") {
                if job["phase"] as? String == "downloading" {
                    ProgressView("正在下载 " + size(job["done"]) + " / " + size(job["total"]), value: (job["done"] as? NSNumber)?.doubleValue ?? 0, total: max(1, (job["total"] as? NSNumber)?.doubleValue ?? 1))
                } else { ProgressView("正在校验和安装 OCR…") }
                HStack { Spacer(); Button("取消 OCR 安装") { Task { _ = try? await m.post("/components/cancel") } } }
            }
            if let error = job["error"] as? String, !error.isEmpty { FormNote(error + " 可点击安装按钮重试。") }
        } header: { Text("OCR 模块 · 按需安装") } footer: {
            FormNote("用于扫描文件和内嵌图片中的文字。可以稍后安装，普通文本、Office 正文及 PDF 文字层仍可读取。点击安装才会下载；下载期间可以继续引导。")
        }
        if !m.running {
            Section { HStack { Text("启动服务以检查已安装组件"); Spacer(); Button("启动服务") { Task { await m.start() } }.disabled(m.starting) } }
        }
        if m.busy { Section { } footer: { FormNote("正在同步资料，完成后即可安装组件。") } }
    }
    func size(_ value: Any?) -> String { researchLibraryFileSize((value as? NSNumber)?.int64Value ?? 0) }
}
