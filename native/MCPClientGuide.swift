import Foundation

enum MCPClient: String, CaseIterable, Identifiable {
    case codex, workbuddy, claudeCode, cursor, vscode, generic
    var id: String { rawValue }
    var name: String {
        switch self {
        case .codex: return "Codex"
        case .workbuddy: return "WorkBuddy"
        case .claudeCode: return "Claude Code"
        case .cursor: return "Cursor"
        case .vscode: return "VS Code"
        case .generic: return "其他客户端 · JSON"
        }
    }
    var formatLabel: String { self == .codex ? "TOML 配置" : (self == .claudeCode ? "终端添加命令" : "JSON 配置") }
    var destination: String {
        switch self {
        case .codex: return "~/.codex/config.toml"
        case .workbuddy: return "~/.workbuddy/mcp.json（用户级）"
        case .claudeCode: return "用户级配置 · 所有项目可用"
        case .cursor: return "~/.cursor/mcp.json（全局）"
        case .vscode: return "项目中的 .vscode/mcp.json"
        case .generic: return "客户端的本地 MCP 配置"
        }
    }
    var steps: String {
        switch self {
        case .codex: return "1. 将下方服务条目合并到 config.toml，保留原有条目。\n2. 在客户端重新加载 MCP，必要时重启客户端。\n3. 在新对话中调用 library_status。"
        case .workbuddy: return "1. 打开“专家·技能·连接器 → 连接器 → 自定义连接器 → 配置 MCP”（旧版入口可能叫“插件”或“技能”）。\n2. 将下方服务合并到 mcpServers 对象，保存配置，保留已有条目。\n3. 返回 MCP 列表，信任 research_library；在新对话中调用 library_status 验证连接。"
        case .claudeCode: return "1. 确认已安装 Claude Code，并打开 macOS 终端。\n2. 复制并运行下方命令，将服务添加到用户级配置。\n3. 运行 claude mcp get research_library 检查条目；在 Claude Code 中用 /mcp 查看连接状态，再调用 library_status。"
        case .cursor: return "1. 打开 Cursor 设置中的 MCP 页面，或编辑 ~/.cursor/mcp.json。\n2. 将下方服务合并到 mcpServers 对象并保存。\n3. 启用该服务器，按客户端提示确认工具使用，再调用 library_status。"
        case .vscode: return "1. 打开项目中的 .vscode/mcp.json；也可通过命令面板进入 MCP 配置。\n2. 将下方服务合并到 servers 对象并保存。\n3. 使用 MCP: List Servers 启动服务器；按客户端提示确认信任，在聊天中调用 library_status。"
        case .generic: return "1. 确认客户端支持本地 STDIO 服务。\n2. 如果客户端接受 mcpServers JSON，合并下方配置；若使用表单，选择 STDIO，命令填下方启动路径，参数留空。\n3. 重新加载服务器，并调用 library_status。仅支持远程 URL 的客户端不能直接使用此配置。"
        }
    }
    var documentation: String {
        switch self {
        case .codex: return "https://developers.openai.com/codex/mcp"
        case .workbuddy: return "https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide"
        case .claudeCode: return "https://code.claude.com/docs/en/mcp"
        case .cursor: return "https://docs.cursor.com/context/model-context-protocol"
        case .vscode: return "https://code.visualstudio.com/docs/agents/reference/mcp-configuration"
        case .generic: return "https://modelcontextprotocol.io/docs/develop/connect-local-servers"
        }
    }
    func configuration(root: URL) -> String {
        if self == .codex { return MCPConfiguration.text(root: root, format: "toml") }
        if self == .claudeCode {
            return "claude mcp add --transport stdio --scope user \(MCPConfiguration.serverName) -- \(Self.shellQuote(MCPConfiguration.command(root: root)))\n"
        }
        if self == .vscode {
            let value: [String: Any] = ["servers": [MCPConfiguration.serverName: ["type": "stdio", "command": MCPConfiguration.command(root: root), "args": [String]()]]]
            let data = try! JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
            return String(decoding: data, as: UTF8.self) + "\n"
        }
        return MCPConfiguration.text(root: root, format: "json")
    }
    static func shellQuote(_ value: String) -> String { "'" + value.replacingOccurrences(of: "'", with: "'\"'\"'") + "'" }
    static let verificationPrompt = "请使用 research_library 的 library_status 工具，报告资料库状态、文档数量和来源文件夹。如果工具不可用，请明确告诉我，不要用其他来源代替。"
}
