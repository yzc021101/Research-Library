using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;
namespace ResearchLibrary;
internal static class Program {
 [STAThread]
 static void Main(string[] args){
  if(args.Contains("--prepare-uninstall")){Environment.Exit(UninstallSupport.Prepare());return;}
  if(args.Contains("--verify-runtime-download")){try{Task.Run(RuntimeSetup.Download).GetAwaiter().GetResult();Environment.Exit(0);}catch{Environment.Exit(1);}return;}
  if(!RuntimeSetup.Ensure())return;
  RunApplication();
 }
 [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.NoInlining)]
 static void RunApplication(){
  WinRT.ComWrappersSupport.InitializeComWrappers();
  var current=AppInstance.FindOrRegisterForKey("research_library.windows."+Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(Engine.Root))));
  if(!current.IsCurrent){
   // Keep the STA free of an async continuation before Application.Start.
   Task.Run(async()=>await current.RedirectActivationToAsync(AppInstance.GetCurrent().GetActivatedEventArgs())).GetAwaiter().GetResult();return;
  }
  current.Activated+=(_,_)=>App.ShowExisting();
  Application.Start(parameters=>{
   SynchronizationContext.SetSynchronizationContext(new DispatcherQueueSynchronizationContext(DispatcherQueue.GetForCurrentThread()));
   _=new App();
  });
 }
}
