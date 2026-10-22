using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Diagnostics;
using System.Text.Json.Nodes;
namespace ResearchLibrary;
public sealed partial class MainWindow {
 StackPanel? updatePanel;string updateFingerprint="";bool updateWorking;
 JsonObject updateState=new();
 readonly DispatcherTimer updateTimer=new(){Interval=TimeSpan.FromMinutes(30)};
 string UpdateVersion { get { try{return JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"distribution.json")))?["version"]?.ToString()??"0.6.7";}catch{return "0.6.7";} } }
 void ReadUpdate(){try{using var stream=new FileStream(Path.Combine(Engine.Root,"updates","state.json"),FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete);updateState=JsonNode.Parse(stream)!.AsObject();}catch{}}
 async Task<bool> RunUpdate(string action,bool automatic=false){
  if(updateWorking)return false;updateWorking=true;updateFingerprint="";UpdateSoftware();
  try{
   var info=Engine.ProcessInfo("updater");info.RedirectStandardError=true;info.RedirectStandardOutput=true;
   foreach(var a in new[]{action,"--current",UpdateVersion,"--target",AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar),"--pid",Environment.ProcessId.ToString()})info.ArgumentList.Add(a);
   if(automatic)info.ArgumentList.Add("--automatic");
   using var p=Process.Start(info)??throw new IOException("无法启动更新程序");
   var err=p.StandardError.ReadToEndAsync();var output=p.StandardOutput.ReadToEndAsync();await p.WaitForExitAsync();
   var message=await err;await output;
   if(p.ExitCode!=0&&!string.IsNullOrWhiteSpace(message))Notify("更新未完成",message,InfoBarSeverity.Warning);
   return p.ExitCode==0;
  }catch(Exception e){Notify("更新未完成",e.Message,InfoBarSeverity.Warning);return false;}
  finally{updateWorking=false;ReadUpdate();UpdateSoftware();}
 }
 Task BeginUpdate(string action){_=RunUpdate(action);return Task.CompletedTask;}
 async Task AutomaticUpdate(){if(Engine.DiskSettings()["automatic_updates"]?.GetValue<bool>()==true)await RunUpdate("check",true);}
 async Task InitializeUpdates(){await RunUpdate("finish");await AutomaticUpdate();updateTimer.Tick+=async(_,_)=>await AutomaticUpdate();updateTimer.Start();}
 void SoftwareSettings(){
  Heading("软件更新");
  var automatic=new ToggleSwitch{MinWidth=0,IsOn=settings["automatic_updates"]?.GetValue<bool>()==true,OnContent="开",OffContent="关"};Identify(automatic,"AutomaticUpdates","自动更新");
  automatic.Toggled+=async(_,_)=>{try{await Save(new{automatic_updates=automatic.IsOn});if(automatic.IsOn)await AutomaticUpdate();}catch(Exception e){Notify("无法保存更新设置",e.Message,InfoBarSeverity.Error);}};
  Body.Children.Add(Card(Row(Text("自动更新",16),automatic)));
  updatePanel=new StackPanel{Spacing=10};Body.Children.Add(updatePanel);updateFingerprint="";UpdateSoftware();
  Note("开启后每天从 GitHub 检查并下载正式版本，安装前由你选择重启。保留资料库、模型和 MCP 配置。更新需要至少 5 GB 空闲空间。");
 }
 void UpdateSoftware(){
  ReadUpdate();if(updatePanel==null)return;
  var fingerprint=updateState.ToJsonString()+updateWorking;if(fingerprint==updateFingerprint)return;updateFingerprint=fingerprint;updatePanel.Children.Clear();
  var check=Button("检查更新",()=>BeginUpdate("check"));check.IsEnabled=!updateWorking;Identify(check,"CheckUpdates","检查更新");
  updatePanel.Children.Add(Card(Row(Text("当前版本 "+UpdateVersion,16),check)));
  string phase=S(updateState,"phase");var release=updateState["release"];
  if(phase is "available" or "ready" or "downloading" or "preparing"){
   var actions=new StackPanel{Spacing=8,Orientation=Orientation.Horizontal};
   actions.Children.Add(Button("更新说明",async()=>{await Windows.System.Launcher.LaunchUriAsync(new Uri(S(release,"release_url",Engine.ReleaseURL)));}));
   if(phase=="available"){var b=Button("下载更新",()=>BeginUpdate("download"),true);Identify(b,"DownloadUpdate","下载更新");b.IsEnabled=!updateWorking;actions.Children.Add(b);}
   if(phase=="ready"){var b=Button("安装并重启…",InstallUpdate,true);Identify(b,"InstallUpdate","安装并重启");b.IsEnabled=!updateWorking&&status["busy"]?.GetValue<bool>()!=true&&S(status["model_job"],"phase") is not ("starting" or "downloading" or "indexing" or "ready");actions.Children.Add(b);}
   updatePanel.Children.Add(Card(Row(Text("新版本 "+S(release,"version"),16),actions)));
  }
  if(updateWorking){
   updatePanel.Children.Add(new ProgressBar{Minimum=0,Maximum=Math.Max(1,updateState["total"]?.GetValue<long>()??1),Value=updateState["done"]?.GetValue<long>()??0,IsIndeterminate=phase!="downloading"});
   if(phase=="downloading")updatePanel.Children.Add(Button("取消下载",()=>{File.WriteAllText(Path.Combine(Engine.Root,"updates","cancel"),"");return Task.CompletedTask;}));
  }
  string message=S(updateState,"error");if(message.Length==0)message=S(updateState,"message");if(message.Length>0)updatePanel.Children.Add(Text(message,14,true));
 }
 async Task InstallUpdate(){
  var dialog=new ContentDialog{XamlRoot=Shell.XamlRoot,Title="安装更新并重启投研纵览？",Content="会短暂停止本地服务，替换 App 后重新打开。来源文件、索引和设置保留。如 MCP 客户端仍占用程序，请先关闭连接。",PrimaryButtonText="安装并重启",CloseButtonText="取消"};
  if(await dialog.ShowAsync()!=ContentDialogResult.Primary)return;
  bool wasRunning=await engine.Running();if(wasRunning)await engine.Stop();
  if(await RunUpdate("install")){updateTimer.Stop();await Quit();}
  else if(wasRunning)await engine.Start();
 }
}
