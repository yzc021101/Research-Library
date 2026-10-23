using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Diagnostics;
using System.Text.Json.Nodes;
namespace ResearchLibrary;
public sealed partial class MainWindow {
 StackPanel? updatePanel;string updateFingerprint="";bool updateWorking;
 JsonObject updateState=new();
 Window? updateProgressWindow; TextBlock? updateProgressTitle,updateProgressSize,updateProgressMessage; ProgressBar? updateProgressBar; Button? updateCancel;
 string previousUpdatePhase="";
 readonly DispatcherTimer progressTimer=new(){Interval=TimeSpan.FromSeconds(1)};
 void ShowUpdateProgress(){
  if(updateProgressWindow==null){
   var window=new Window{Title="更新投研纵览",SystemBackdrop=new Microsoft.UI.Xaml.Media.MicaBackdrop()};
   var panel=new StackPanel{Padding=new Thickness(24),Spacing=18};
   updateProgressTitle=Text("正在更新",22);updateProgressBar=new ProgressBar{Minimum=0,Maximum=1};updateProgressSize=Text("",14,true);updateProgressMessage=Text("",14,true);
   updateCancel=Button("取消下载",()=>{File.WriteAllText(Path.Combine(Engine.Root,"updates","cancel"),"");return Task.CompletedTask;});updateCancel.HorizontalAlignment=HorizontalAlignment.Right;
   foreach(var item in new UIElement[]{updateProgressTitle,updateProgressBar,updateProgressSize,updateProgressMessage,updateCancel})panel.Children.Add(item);
   window.Content=panel;var scale=Shell.XamlRoot?.RasterizationScale??1;window.AppWindow.Resize(new Windows.Graphics.SizeInt32((int)(520*scale),(int)(300*scale)));
   window.Closed+=(_,_)=>{updateProgressWindow=null;};updateProgressWindow=window;
  }
  RefreshUpdateProgress();updateProgressWindow.Activate();
 }
 void RefreshUpdateProgress(){
  if(updateProgressWindow==null)return;
  string phase=S(updateState,"phase");
  updateProgressTitle!.Text=phase switch{"downloading"=>"正在下载更新","verifying"=>"正在校验下载","preparing" or "prepared"=>"正在安装更新","ready"=>"下载完成","current"=>"更新完成","error"=>"更新未完成","cancelled"=>"下载已取消",_=>"正在检查更新"};
  long done=updateState["done"]?.GetValue<long>()??0,total=updateState["total"]?.GetValue<long>()??0;
  updateProgressBar!.Maximum=Math.Max(1,total);updateProgressBar.Value=Math.Min(done,Math.Max(1,total));updateProgressBar.IsIndeterminate=phase is "preparing" or "prepared" or "checking";
  updateProgressSize!.Text=$"{UpdateBytes(done)} / {UpdateBytes(total)}";updateProgressSize.Visibility=phase is "downloading" or "ready" or "verifying"?Visibility.Visible:Visibility.Collapsed;
  updateProgressMessage!.Text=S(updateState,"error");if(updateProgressMessage.Text.Length==0)updateProgressMessage.Text=S(updateState,"message");
  updateCancel!.Visibility=phase=="downloading"?Visibility.Visible:Visibility.Collapsed;
 }
 static string UpdateBytes(long value)=>value>=1024*1024?$"{value/(1024d*1024):N1} MB":$"{value/1024d:N0} KB";
 void PollUpdateProgress(){
  ReadUpdate();string phase=S(updateState,"phase");
  if(phase!=previousUpdatePhase){previousUpdatePhase=phase;if(phase is "downloading" or "preparing")ShowUpdateProgress();}
  RefreshUpdateProgress();UpdateSoftware();
 }

 readonly DispatcherTimer updateTimer=new(){Interval=TimeSpan.FromMinutes(30)};
 string UpdateVersion { get { try{return JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"distribution.json")))?["version"]?.ToString()??"0.6.12";}catch{return "0.6.12";} } }
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
 async Task InitializeUpdates(){progressTimer.Tick+=(_,_)=>PollUpdateProgress();progressTimer.Start();await RunUpdate("finish");await AutomaticUpdate();updateTimer.Tick+=async(_,_)=>await AutomaticUpdate();updateTimer.Start();}
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
   var buttons=new List<Button>();
   buttons.Add(Button("更新说明",async()=>{await Windows.System.Launcher.LaunchUriAsync(new Uri(S(release,"release_url",Engine.ReleaseURL)));}));
   if(phase=="available"){var b=Button("下载更新",()=>BeginUpdate("download"),true);Identify(b,"DownloadUpdate","下载更新");b.IsEnabled=!updateWorking;buttons.Add(b);}
   if(phase=="ready"){var b=Button("安装并重启…",InstallUpdate,true);Identify(b,"InstallUpdate","安装并重启");b.IsEnabled=!updateWorking&&status["busy"]?.GetValue<bool>()!=true&&S(status["model_job"],"phase") is not ("starting" or "downloading" or "indexing" or "ready");buttons.Add(b);}
   updatePanel.Children.Add(Card(Row(Text("新版本 "+S(release,"version"),16),AdaptiveLayout.Actions(buttons))));
  }
  if(phase is "downloading" or "verifying" or "preparing" or "prepared" or "ready")updatePanel.Children.Add(Button("查看更新进度",()=>{ShowUpdateProgress();return Task.CompletedTask;}));
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
  if(await RunUpdate("install")){updateTimer.Stop();progressTimer.Stop();updateProgressWindow?.Close();await Quit();}
  else if(wasRunning)await engine.Start();
 }
}
