using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
namespace ResearchLibrary;

internal static class UninstallSupport {
 internal static string EventName=>@"Local\research_library.quit."+Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Path.GetFullPath(AppContext.BaseDirectory).ToUpperInvariant())));
 internal static int Prepare(){
  try{
   using(var signal=new EventWaitHandle(false,EventResetMode.AutoReset,EventName))signal.Set();
   string app=Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,"ResearchLibrary.Windows.exe"));
   string engine=Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,"engine","research-library-engine.exe"));
   // Only inspect processes using this installation's two exact executables.
   // The running app handles graceful shutdown, including its owned service.
   for(int attempt=0;attempt<100;attempt++){
    bool running=false;
    foreach(var process in Process.GetProcesses())using(process){
     if(process.Id==Environment.ProcessId)continue;
     try{string? path=process.MainModule?.FileName;
      if(string.Equals(path,app,StringComparison.OrdinalIgnoreCase)||string.Equals(path,engine,StringComparison.OrdinalIgnoreCase))running=true;
     }catch(System.ComponentModel.Win32Exception){}catch(InvalidOperationException){}
    }
    if(!running)return 0;
    Thread.Sleep(100);
   }
   return 1;
  }catch{return 2;}
 }
}
