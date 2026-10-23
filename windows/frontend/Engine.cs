using System.Diagnostics;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
namespace ResearchLibrary;
public sealed class Engine {
 public static string Runtime => Path.Combine(AppContext.BaseDirectory,"engine","research-library-engine.exe");
 public const string ReleaseURL="https://github.com/yzc021101/Research-Library/releases";
 // Development mode is opt-in; releases always use their bundled engine.
 public static bool Packaged => string.IsNullOrEmpty(Environment.GetEnvironmentVariable("RESEARCH_LIBRARY_DEV_ROOT")) || File.Exists(Path.Combine(AppContext.BaseDirectory,"distribution.json"));
 public static bool Available => File.Exists(Packaged?Runtime:Path.Combine(Root,".venv","Scripts","python.exe"));
 public static readonly string Root = Environment.GetEnvironmentVariable("RESEARCH_LIBRARY_ROOT") ?? (Packaged ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"research_library") : Environment.GetEnvironmentVariable("RESEARCH_LIBRARY_DEV_ROOT")!);
 static Engine(){
  foreach(var name in new[]{"data","logs","tmp","cache","inbox","components"})Directory.CreateDirectory(Path.Combine(Root,name));
  var file=Path.Combine(Root,"data","settings.json");
  if(!File.Exists(file))File.WriteAllText(file,JsonSerializer.Serialize(new{source_folders=new[]{Path.Combine(Root,"inbox")},top_k=8,search_mode="hybrid",auto_scan=true,scan_interval=30,start_service_on_launch=true,keep_in_menu_bar=true,app_managed=true}));
 }
 public static ProcessStartInfo ProcessInfo(string mode){
  var info=new ProcessStartInfo(Packaged?Runtime:Path.Combine(Root,".venv","Scripts","python.exe")){WorkingDirectory=Root,UseShellExecute=false,CreateNoWindow=true};
  if(Packaged)info.ArgumentList.Add(mode);else{info.ArgumentList.Add("-B");info.ArgumentList.Add(Path.Combine(Root,"src",mode+".py"));}
  info.Environment["RESEARCH_LIBRARY_ROOT"]=Root;info.Environment["PYTHONUTF8"]="1";return info;
 }
 private readonly HttpClient http=new(){Timeout=TimeSpan.FromSeconds(180)};
 private Process? owned;
 public async Task<JsonObject> Request(string route, object? body=null,CancellationToken cancellationToken=default){
  var info=JsonNode.Parse(await File.ReadAllTextAsync(Path.Combine(Root,"data","service.json")))!;
  int port=info["port"]!.GetValue<int>(); if(port<1||port>65535)throw new IOException("服务端口无效");
  using var req=new HttpRequestMessage(body==null?HttpMethod.Get:HttpMethod.Post,$"http://127.0.0.1:{port}{route}");
  req.Headers.Authorization=new AuthenticationHeaderValue("Bearer",info["token"]!.GetValue<string>());
  if(body!=null)req.Content=new StringContent(JsonSerializer.Serialize(body),Encoding.UTF8,"application/json");
  using var res=await http.SendAsync(req,cancellationToken);var data=JsonNode.Parse(await res.Content.ReadAsStringAsync(cancellationToken))!.AsObject();
  if(!res.IsSuccessStatusCode)throw new IOException(data["error"]?.ToString()??res.StatusCode.ToString());return data;
 }
 public async Task<bool> Running(){try{using var timeout=new CancellationTokenSource(1500);await Request("/status",cancellationToken:timeout.Token);return true;}catch{return false;}}
 public async Task Start(){
  if(await Running())return;
  if(!Available)throw new IOException("运行环境缺失。请到设置 → 运行环境与可选组件下载完整安装包；解压时保留整个文件夹，无需单独安装 Python。");
  var info=ProcessInfo("backend");info.RedirectStandardError=true;info.RedirectStandardOutput=true;
  info.Environment["PYTHONUTF8"]="1";info.Environment["PYTHONDONTWRITEBYTECODE"]="1";
  owned=Process.Start(info)??throw new IOException("未能启动资料库服务");
  _=Log(owned.StandardError,"backend-stderr.log");_=Log(owned.StandardOutput,"backend-stdout.log");
  for(int i=0;i<50;i++){if(await Running())return;if(owned.HasExited)throw new IOException("服务未能启动，请查看 app\\logs 中的日志。");await Task.Delay(200);}
  throw new TimeoutException("服务启动超时，请重试。");
 }
 private static async Task Log(StreamReader reader,string name){
  // Drain long-running backend logs incrementally instead of retaining them until exit.
  using var writer=new StreamWriter(new FileStream(Path.Combine(Root,"logs",name),FileMode.Append,FileAccess.Write,FileShare.ReadWrite)){AutoFlush=true};
  var buffer=new char[4096];int count;
  while((count=await reader.ReadAsync(buffer.AsMemory()))>0)await writer.WriteAsync(buffer.AsMemory(0,count));
 }
 public async Task Stop(){
  await Request("/shutdown",new{});
  for(int i=0;i<40;i++){if(!await Running())return;await Task.Delay(200);}
  throw new TimeoutException("服务仍在结束任务，请稍后检查状态。");
 }
 public async Task<JsonObject> SaveSettings(object value){
  if(await Running())return await Request("/settings",value);
  var info=ProcessInfo("settings_cli");info.RedirectStandardInput=true;info.RedirectStandardOutput=true;info.RedirectStandardError=true;
  using var process=Process.Start(info)??throw new IOException("无法保存设置。");
  var output=process.StandardOutput.ReadToEndAsync();var error=process.StandardError.ReadToEndAsync();
  await process.StandardInput.WriteAsync(JsonSerializer.Serialize(value));process.StandardInput.Close();await process.WaitForExitAsync();
  if(process.ExitCode!=0)throw new IOException(await error);
  return JsonNode.Parse(await output)!.AsObject();
 }
 public async Task CloseOwned(){if(owned!=null&&!owned.HasExited){try{await Stop();await owned.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(8));}catch{if(!owned.HasExited)owned.Kill(true);}}}
 public Task<JsonObject> Tool(string name,object? arguments=null)=>Request("/tool",new{name,arguments=arguments??new{}});
 public static JsonObject DiskSettings()=>JsonNode.Parse(File.ReadAllText(Path.Combine(Root,"data","settings.json")).TrimStart('\uFEFF'))!.AsObject();
}
public static class MCPConfiguration {
 public const string Name="research_library";
 public static string Python=>Path.Combine(Engine.Root,".venv","Scripts","python.exe");
 public static string Server=>Path.Combine(Engine.Root,"src","server.py");
 public static string Create(string client){
  if(Engine.Packaged){
   string command=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"cmd.exe");
   string launcher=Path.Combine(Engine.Root,"run-mcp.cmd");
   if(client=="Codex")return $"[mcp_servers.{Name}]\ncommand = '{command}'\nargs = ['/d', '/c', '{launcher}']\nstartup_timeout_sec = 180\ntool_timeout_sec = 180\n\n[mcp_servers.{Name}.env]\nRESEARCH_LIBRARY_ROOT = '{Engine.Root}'\nRESEARCH_LIBRARY_ENGINE = '{Engine.Runtime}'\n";
   if(client=="Claude Code")return $"claude mcp add --transport stdio --scope user --env RESEARCH_LIBRARY_ROOT=\"{Engine.Root}\" --env RESEARCH_LIBRARY_ENGINE=\"{Engine.Runtime}\" {Name} -- \"{command}\" /d /c \"{launcher}\"";
   var packagedServer=new JsonObject{["command"]=command,["args"]=new JsonArray("/d","/c",launcher),["env"]=new JsonObject{["RESEARCH_LIBRARY_ROOT"]=Engine.Root,["RESEARCH_LIBRARY_ENGINE"]=Engine.Runtime}};
   if(client=="VS Code")packagedServer["type"]="stdio";
   return new JsonObject{[client=="VS Code"?"servers":"mcpServers"]=new JsonObject{[Name]=packagedServer}}.ToJsonString(new JsonSerializerOptions{WriteIndented=true});
  }
  if(client=="Codex")return $"[mcp_servers.{Name}]\ncommand = '{Python}'\nargs = ['-B', '{Server}']\nstartup_timeout_sec = 180\ntool_timeout_sec = 180\n\n[mcp_servers.{Name}.env]\nPYTHONUTF8 = '1'\n";
  if(client=="Claude Code")return $"claude mcp add --transport stdio --scope user {Name} -- \"{Python}\" -B \"{Server}\"";
  var server=new JsonObject{["command"]=Python,["args"]=new JsonArray("-B",Server),["env"]=new JsonObject{["PYTHONUTF8"]="1"}};
  if(client=="VS Code")server["type"]="stdio";
  return new JsonObject{[client=="VS Code"?"servers":"mcpServers"]=new JsonObject{[Name]=server}}.ToJsonString(new JsonSerializerOptions{WriteIndented=true});
 }
 public static string Destination(string client)=>client switch{"Codex"=>@"%USERPROFILE%\.codex\config.toml","WorkBuddy"=>@"%USERPROFILE%\.workbuddy\mcp.json","Cursor"=>@"%USERPROFILE%\.cursor\mcp.json","VS Code"=>@"项目目录\.vscode\mcp.json","Claude Code"=>"在 PowerShell 中执行，写入用户级配置",_=>"客户端的本地 MCP 配置"};
 public static string Steps(string client)=>client switch{
  "Codex"=>"1. 将下方服务条目合并到 config.toml，保留已有配置。\n2. 重新加载 MCP，必要时重启客户端。\n3. 调用 library_status 检查资料库。",
  "WorkBuddy"=>"1. 在连接器的 MCP 配置入口打开配置文件（不同版本入口名称可能不同）。\n2. 将下方 research_library 条目合并到 mcpServers，保存并保留其他服务。\n3. 在 MCP 列表启用并按提示信任该服务，再调用 library_status。",
  "Claude Code"=>"1. 确认已安装 Claude Code，打开 Windows PowerShell。\n2. 运行下方命令添加用户级服务；已有同名条目时先检查，避免重复配置。\n3. 用 claude mcp get research_library 检查条目，在 Claude Code 中用 /mcp 查看状态。",
  "Cursor"=>"1. 打开 Cursor 的 MCP 设置或下方全局配置文件。\n2. 将服务条目合并到 mcpServers，保留已有条目。\n3. 启用服务器，按客户端提示允许工具使用，再调用 library_status。",
  "VS Code"=>"1. 打开项目中的 .vscode/mcp.json。\n2. 将服务条目合并到 servers 并保存。\n3. 使用 MCP: List Servers 启动服务，按提示确认信任，再调用 library_status。",
  _=>"1. 确认客户端支持本地 STDIO。\n2. 合并下方 JSON；表单模式需分别填写 command、args 和 env，不能只填启动路径。\n3. 重新加载并调用 library_status。仅支持远程 URL 的客户端无法直接使用此配置。"};
 public const string Verify="请调用 research_library 的 library_status，报告文档数量和来源文件夹，再用 search_passages 检索指定资料并用 read_unit 返回原文及准确位置（PDF 页码、幻灯片、正文块、工作表单元格或行号）。含 OCR 时请取回图片核验。工具不可用时请明确说明。";
}
