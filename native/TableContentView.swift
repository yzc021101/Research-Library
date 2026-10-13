import AppKit
import SwiftUI

struct SourceTable: Identifiable {
    struct Column: Identifiable { let id: String; let label: String; let width: CGFloat }
    struct Cell { let text: String; let detail: String }
    struct Row: Identifiable { let id: Int; let label: String; let cells: [String: Cell] }
    let id = UUID()
    let title: String
    let context: String
    let columns: [Column]
    let rows: [Row]
    init(_ value: [String: Any]) {
        title = value["title"] as? String ?? "表格"
        context = value["context"] as? String ?? ""
        rows = (value["rows"] as? [[String: Any]] ?? []).enumerated().map { offset, row in
            let cells = (row["cells"] as? [String: [String: Any]] ?? [:]).mapValues { cell in
                let text = (cell["text"] as? String ?? "") + ((cell["truncated"] as? Bool == true) ? "\n…内容较长，请打开原文件查看完整单元格" : "")
                let coordinate = cell["coordinate"] as? String ?? ""
                let format = cell["number_format"] as? String ?? ""
                let formula = cell["formula"] as? String ?? ""
                return Cell(text: text, detail: [coordinate, format == "General" ? "" : format, formula].filter { !$0.isEmpty }.joined(separator: " · "))
            }
            return Row(id: offset, label: String(describing: row["index"] ?? offset+1), cells: cells)
        }
        let sourceRows = rows
        columns = (value["columns"] as? [[String: String]] ?? []).map { column in
            let key = column["key"] ?? ""
            let longest = sourceRows.map { $0.cells[key]?.text.count ?? 0 }.max() ?? 0
            return Column(id: key, label: column["label"] ?? key, width: longest > 45 ? 260 : longest > 16 ? 200 : 140)
        }
    }
    static func parse(_ value: Any?) -> [SourceTable] {
        (value as? [[String: Any]] ?? []).map(SourceTable.init)
    }
}

struct TableContentView: View {
    let table: SourceTable
    var preview = false
    private func cell(_ text: String, width: CGFloat, header: Bool = false) -> some View {
        Text(text.isEmpty ? " " : text)
            .font(.system(size: 14, weight: header ? .semibold : .regular))
            .textSelection(.enabled)
            .fixedSize(horizontal: false, vertical: true)
            .frame(width: width - 20, alignment: .topLeading)
            .padding(10)
            .frame(maxHeight: .infinity, alignment: .topLeading)
            .background(header ? Color(nsColor: .controlBackgroundColor) : Color(nsColor: .textBackgroundColor))
            .overlay(alignment: .trailing) { Rectangle().fill(Color.primary.opacity(0.10)).frame(width: 1) }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(table.title).font(.headline)
            if !table.context.isEmpty {
                Text(table.context).font(.callout).foregroundStyle(.secondary).lineLimit(3).help(table.context)
            }
            ScrollView([.horizontal, .vertical]) {
                Grid(alignment: .topLeading, horizontalSpacing: 0, verticalSpacing: 0) {
                    GridRow {
                        cell("行", width: 60, header: true)
                        ForEach(table.columns) { column in cell(column.label, width: column.width, header: true) }
                    }
                    ForEach(table.rows) { row in
                        GridRow {
                            cell(row.label, width: 60, header: true)
                            ForEach(table.columns) { column in
                                cell(row.cells[column.id]?.text ?? "", width: column.width)
                                    .help(row.cells[column.id]?.detail ?? "")
                            }
                        }
                        .overlay(alignment: .bottom) { Rectangle().fill(Color.primary.opacity(0.10)).frame(height: 1) }
                    }
                }
                .padding(.bottom, 14)
            }
            .frame(maxHeight: preview ? 460 : 340)
            .fixedSize(horizontal: false, vertical: true)
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.primary.opacity(0.15)))
            .accessibilityLabel("原文表格，\(table.rows.count) 行，\(table.columns.count) 列")
            Text("左右滚动查看全部列；空白格保持为空。公式显示已保存的结果，未重新计算；悬停可查看公式及数字格式。")
                .font(.callout).foregroundStyle(.secondary)
        }
    }
}
