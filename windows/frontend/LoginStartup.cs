using Microsoft.Win32;
namespace ResearchLibrary;
internal static class LoginStartup {
 const string Key=@"Software\Microsoft\Windows\CurrentVersion\Run",Name="research_library";
 static string Command=>$"\"{Environment.ProcessPath ?? throw new IOException("无法确定应用路径。")}\" --background";
 public static bool Enabled {get{using var key=Registry.CurrentUser.OpenSubKey(Key);return string.Equals(key?.GetValue(Name) as string,Command,StringComparison.OrdinalIgnoreCase);}}
 // Only an explicit settings action calls this. Never modify another application's entry.
 public static void Set(bool enabled){
  using var key=Registry.CurrentUser.CreateSubKey(Key,true)??throw new IOException("无法访问当前用户的登录项。");
  string? existing=key.GetValue(Name) as string;
  if(key.GetValue(Name)!=null&&!string.Equals(existing,Command,StringComparison.OrdinalIgnoreCase))throw new IOException("同名登录项指向其他位置，未作修改。请先检查系统启动应用设置。");
  if(enabled)key.SetValue(Name,Command,RegistryValueKind.String);else if(existing!=null)key.DeleteValue(Name,false);
 }
}
