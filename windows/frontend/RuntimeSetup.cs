using System.Net.Http;
using System.Diagnostics;
using System.Net;
using System.Runtime.InteropServices;
using System.Text.Json;
namespace ResearchLibrary;
internal static class RuntimeSetup {
 internal const string DownloadUrl="https://aka.ms/vc14/vc_redist.x64.exe";
 internal const string GuideUrl="https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist";
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] static extern int MessageBoxW(IntPtr window,string message,string title,uint flags);
 internal static bool Available(){
  foreach(var name in new[]{"vcruntime140.dll","vcruntime140_1.dll","msvcp140.dll","msvcp140_atomic_wait.dll"}){
   if(!NativeLibrary.TryLoad(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),name),out var handle))return false;
   NativeLibrary.Free(handle);
  }
  return true;
 }
 internal static async Task<string> Download(){
  string folder=Path.Combine(Engine.Root,"runtime","downloads");Directory.CreateDirectory(folder);
  string output=Path.Combine(folder,"vc_redist.x64.exe"),partial=output+".partial";
  using var handler=new HttpClientHandler{AllowAutoRedirect=false};using var client=new HttpClient(handler){Timeout=TimeSpan.FromMinutes(10)};
  var uri=new Uri(DownloadUrl);
  try {
   for(int i=0;i<8;i++){
    if(uri.Scheme!="https")throw new IOException("下载地址必须使用 HTTPS。");
    using var response=await client.GetAsync(uri,HttpCompletionOption.ResponseHeadersRead);
    if((int)response.StatusCode>=300&&(int)response.StatusCode<400){uri=new Uri(uri,response.Headers.Location??throw new IOException("下载重定向缺少地址。"));continue;}
    response.EnsureSuccessStatusCode();long expected=response.Content.Headers.ContentLength??0;
    if(expected>100*1024*1024)throw new IOException("运行库安装程序大小异常。");
    using(var destination=File.Create(partial)){using var input=await response.Content.ReadAsStreamAsync();byte[] buffer=new byte[65536];long count=0;int n;
     while((n=await input.ReadAsync(buffer))>0){count+=n;if(count>100*1024*1024)throw new IOException("运行库安装程序大小异常。");await destination.WriteAsync(buffer.AsMemory(0,n));}
     if(expected>0&&count!=expected)throw new IOException("下载未完成，请重试。");
    }
    // Authenticode validates the Windows trust chain and publisher, independently of redirects.
    var start=new ProcessStartInfo{FileName=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"WindowsPowerShell","v1.0","powershell.exe"),UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
    start.ArgumentList.Add("-NoProfile");start.ArgumentList.Add("-NonInteractive");start.ArgumentList.Add("-Command");
    start.ArgumentList.Add("$s=Get-AuthenticodeSignature -LiteralPath '"+partial.Replace("'","''")+"';if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch '(^|,\\s*)O=Microsoft Corporation(,|$)'){exit 1};exit 0");
    using var check=Process.Start(start)??throw new IOException("无法校验微软签名。");await check.WaitForExitAsync();if(check.ExitCode!=0)throw new IOException("微软数字签名校验失败，已拒绝运行。");
    File.Move(partial,output,true);return output;
   }
   throw new IOException("下载重定向次数过多。");
  } finally {if(File.Exists(partial))File.Delete(partial);}
 }
 internal static async Task Install(){
  var file=await Download();
  using var installer=Process.Start(new ProcessStartInfo(file){UseShellExecute=true})??throw new IOException("无法打开微软安装程序。");
  await installer.WaitForExitAsync();
  if(installer.ExitCode!=0&&installer.ExitCode!=3010&&installer.ExitCode!=1638)throw new IOException("微软运行库未完成安装，可再次重试。");
 }
 internal static bool Ensure(){
  if(Available())return true;
  if(MessageBoxW(IntPtr.Zero,"需要安装 Microsoft Visual C++ x64 运行库。点击“是”从微软官网下载并校验安装程序；请在微软窗口中阅读许可并确认安装。安装可能需要管理员授权。\n\n下载期间请稍候，完成后将打开 App。","投研纵览 · 准备运行环境",0x24)!=6)return false;
  try{Task.Run(Install).GetAwaiter().GetResult();if(!Available())throw new IOException("运行库仍未就绪。如安装程序要求重启，请重启 Windows 后再打开 App。");return true;}
  catch(Exception e){MessageBoxW(IntPtr.Zero,e.Message+"\n官方下载说明："+GuideUrl,"运行环境安装未完成",0x10);return false;}
 }
}
