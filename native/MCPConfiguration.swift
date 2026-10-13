import Foundation

enum AppRuntime {
    static var bundled: URL { Bundle.main.bundleURL.appendingPathComponent("Contents/Resources/engine/research-library-engine") }
    static var packaged: Bool { Bundle.main.object(forInfoDictionaryKey: "ResearchLibraryDistribution") as? Bool == true || FileManager.default.isExecutableFile(atPath: bundled.path) }
    static func libraryRoot(defaultRoot: URL) -> URL {
        let pointer = defaultRoot.appendingPathComponent("data-location.json")
        if let data = try? Data(contentsOf: pointer), let value = try? JSONSerialization.jsonObject(with: data) as? [String: String],
           let path = value["root"], path.hasPrefix("/"), FileManager.default.fileExists(atPath: URL(fileURLWithPath: path).appendingPathComponent("data/settings.json").path) {
            return URL(fileURLWithPath: path, isDirectory: true)
        }
        return defaultRoot
    }
    static var releaseURL: URL? {
        let text = Bundle.main.object(forInfoDictionaryKey: "ResearchLibraryReleaseURL") as? String ?? "https://github.com/yzc021101/Research-Library/releases"
        guard
              let url = URL(string: text), url.scheme == "https" else { return nil }
        return url
    }
    static func executable(root: URL) -> URL { packaged ? bundled : root.appendingPathComponent(".venv/bin/python") }
    static func arguments(_ mode: String, root: URL) -> [String] { packaged ? [mode] : ["-B", root.appendingPathComponent("src/\(mode).py").path] }
    static func prepare(root: URL) throws {
        for name in ["data", "logs", "inbox", "tmp", "cache", "components"] {
            try FileManager.default.createDirectory(at: root.appendingPathComponent(name), withIntermediateDirectories: true)
        }
        if packaged {
            let command = "#!/bin/sh\nexport RESEARCH_LIBRARY_ROOT=" + MCPClient.shellQuote(root.path) + "\nexec " + MCPClient.shellQuote(bundled.path) + " server \"$@\"\n"
            let url = root.appendingPathComponent("run.sh")
            try command.write(to: url, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
        }
    }
}

enum MCPConfiguration {
    static let serverName = "research_library"
    static func command(root: URL) -> String { root.appendingPathComponent("run.sh").path }
    static func text(root: URL, format: String) -> String {
        let command = command(root: root)
        if format == "json" {
            let value: [String: Any] = ["mcpServers": [serverName: ["command": command, "args": [String]()]]]
            guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]),
                  let text = String(data: data, encoding: .utf8) else { return "" }
            return text + "\n"
        }
        // JSON string escaping is also valid for this TOML basic string.
        let encoder = JSONEncoder(); encoder.outputFormatting = [.withoutEscapingSlashes]
        guard let data = try? encoder.encode(command), let quoted = String(data: data, encoding: .utf8) else { return "" }
        return """
        [mcp_servers.\(serverName)]
        command = \(quoted)
        args = []
        startup_timeout_sec = 180
        tool_timeout_sec = 180

        """
    }
}
