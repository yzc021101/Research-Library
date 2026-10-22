import SwiftUI
import AppKit
struct StorageSettings: View {
    @ObservedObject var m: LibraryModel
    @State private var info: [String: Any] = [:]
    @State private var working = false
    @State private var result = ""
    let categories = [("snapshots", "原文快照"), ("index", "检索索引"), ("previews", "图片与预览缓存"), ("conversions", "格式转换缓存"), ("models", "向量模型"), ("components", "可选组件")]
    var body: some View {
        Section {
            Toggle("保留原文快照", isOn: $m.preferences.keepSnapshots)
            Picker("缓存保留期限", selection: $m.preferences.cacheRetentionDays) {
                Text("7 天").tag(7); Text("30 天").tag(30); Text("90 天").tag(90); Text("1 年").tag(365)
            }
        } header: { Text("引用与缓存") } footer: {
            Text("默认关联原文件，显示真实文件名。开启快照后，同步时另存一份原文用于版本核对。服务每天清理过期缓存与旧索引；开启时保留当前版本快照。")
        }
        Section {
            ForEach(categories, id: \.0) { key, name in
                LabeledContent(name, value: size(((info["categories"] as? [String: [String: Any]])?[key])?["bytes"]))
            }
            HStack { Text("统计空间占用"); Spacer(); Button("刷新") { Task { await refresh() } } }
            HStack { Text("过期快照、缓存与旧索引"); Spacer(); Button("清理过期内容…") { clean("expired") } }
            HStack { Text("图片、预览和转换缓存"); Spacer(); Button("清理缓存…") { clean("generated") } }
            HStack { Text("全部原文快照"); Spacer(); Button("移除副本…") { clean("snapshots") }.disabled(m.preferences.keepSnapshots) }
            if !result.isEmpty { Text(result).font(.callout).foregroundStyle(.secondary) }
        } header: { Text("空间管理") } footer: {
            Text("清理不会修改来源文件或移除模型。图片缓存可在下次同步或预览时重建；移除快照会使之前指向副本的链接失效。关闭快照后，可在这里移除已有副本。")
        }
        .disabled(working || !m.running || m.busy || m.modelBusy)
        .task { await refresh() }
    }
    func size(_ n: Any?) -> String { guard let n = n as? NSNumber else { return "—" }; return researchLibraryFileSize(n.int64Value) }
    func refresh() async {
        working = true; defer { working = false }
        do { info = try await m.post("/storage/status") } catch { result = error.localizedDescription }
    }
    func clean(_ mode: String) {
        let a = NSAlert(); a.messageText = mode == "snapshots" ? "移除所有原文副本？" : "清理资料库缓存？"
        a.informativeText = "来源文件和当前检索文字会保留。已清理的快照链接将失效；图片与转换缓存需要时可重新生成。"
        a.addButton(withTitle: "清理"); a.addButton(withTitle: "取消")
        guard a.runModal() == .alertFirstButtonReturn else { return }
        Task {
            working = true; defer { working = false }
            do {
                let r = try await m.post("/storage/cleanup", ["mode": mode]); info = r["storage"] as? [String: Any] ?? [:]
                result = "已移除 \(r["removed_files"] as? Int ?? 0) 个缓存文件，释放 \(size(r["released_bytes"]))。"
                if let errors = r["errors"] as? [String], !errors.isEmpty { result += "部分内容未清理：" + errors.joined(separator: "；") }
            } catch { result = error.localizedDescription }
        }
    }
}

func researchLibraryFileSize(_ bytes: Int64) -> String {
    if bytes == 0 { return "0 KB" }
    return ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
}
