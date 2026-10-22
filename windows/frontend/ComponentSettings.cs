using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
using Windows.Storage.Pickers;
using WinRT.Interop;
namespace ResearchLibrary;
public sealed partial class MainWindow {
 StackPanel? componentPanel;string componentFingerprint="";
 void ComponentSettings(){
  Heading("运行环境与可选组件");
  Body.Children.Add(Card(Row(Stack(Text("Microsoft Visual C++ x64 运行库",16),Text(RuntimeSetup.Available()?"系统运行库已就绪":"需要安装微软运行库",14,true)),Button("下载并安装运行库",async()=>{await RuntimeSetup.Install();await Refresh(false);} ))));
  Body.Children.Add(Card(Row(Stack(Text("基础运行环境",16),Text(Engine.Available?"已就绪 · 完整发行版自带 Python、.NET 和基础依赖":"运行环境缺失 · 请下载完整发行版，并保留整个解压目录",14,true)),Button("下载完整安装包",()=>Windows.System.Launcher.LaunchUriAsync(new Uri(Engine.ReleaseURL)).AsTask()))));
  Body.Children.Add(Row(Text("官方组件来源",14),Stack(Button("Python",()=>Windows.System.Launcher.LaunchUriAsync(new Uri("https://www.python.org/downloads/")).AsTask()),Button("OCR",()=>Windows.System.Launcher.LaunchUriAsync(new Uri("https://tesseract-ocr.github.io/tessdoc/Installation.html")).AsTask()),Button("LibreOffice",()=>Windows.System.Launcher.LaunchUriAsync(new Uri("https://www.libreoffice.org/download/download-libreoffice/")).AsTask()))));
  Note("基础运行环境随完整安装包提供，无需单独安装 Python。OCR 和旧版 Office 转换器按需下载，校验后安装到本应用资料库目录。安装或移除后重启服务。系统已有组件只复用，不会被卸载。");
  Body.Children.Add(Row(Text("AGPL-3.0 开源软件",14),Button("许可证与对应源码",()=>Windows.System.Launcher.LaunchUriAsync(new Uri("https://github.com/yzc021101/Research-Library/tree/v0.6.7")).AsTask())));
  componentPanel=new StackPanel{Spacing=12};Body.Children.Add(componentPanel);componentFingerprint="";UpdateComponents();
 }
 static string Size(JsonNode? n)=>$"{(n?.GetValue<long>()??0)/1048576d:F1} MB";
 async Task ImportComponent(JsonNode item){
  var picker=new FileOpenPicker();InitializeWithWindow.Initialize(picker,WindowNative.GetWindowHandle(this));picker.FileTypeFilter.Add(".zip");var file=await picker.PickSingleFileAsync();
  if(file!=null)await engine.Request("/components/install",new{id=S(item,"id"),path=file.Path});await Refresh(false);
 }
 void UpdateComponents(){
  if(componentPanel==null)return;
  var data=status["components"];string fingerprint=data?.ToJsonString()??"offline";if(fingerprint==componentFingerprint)return;componentFingerprint=fingerprint;componentPanel.Children.Clear();
  if(data==null){componentPanel.Children.Add(Text("启动服务后可检查并安装可选组件。基础环境缺失时请使用上方完整安装包入口。",14,true));return;}
  var job=data["job"];bool installing=new[]{"downloading","installing"}.Contains(S(job,"phase"));
  foreach(var node in data["items"]?.AsArray()??new JsonArray()){
   var item=node!;bool installed=item["installed"]?.GetValue<bool>()==true,external=item["external"]?.GetValue<bool>()==true;
   string detail=installed?"已安装 · "+Size(item["installed_bytes"]):external?"复用本机组件，无需重复安装":"下载 "+Size(item["download_bytes"])+" · 安装后 "+Size(item["expanded_bytes"]);
   var actions=new StackPanel{Spacing=8,HorizontalAlignment=HorizontalAlignment.Right};
   if(installed){actions.Children.Add(Button("移除…",async()=>{
     var dialog=new ContentDialog{XamlRoot=Shell.XamlRoot,Title="移除可选组件？",Content="保留已经录入的资料、文字和索引。只移除本应用管理的组件。",PrimaryButtonText="移除",CloseButtonText="取消"};
     if(await dialog.ShowAsync()==ContentDialogResult.Primary)await engine.Request("/components/remove",new{id=S(item,"id")});await Refresh(false);
   }));}else{
    var download=Button("下载并安装",async()=>{await engine.Request("/components/install",new{id=S(item,"id")});await Refresh(false);});
    download.IsEnabled=!external&&!string.IsNullOrWhiteSpace(S(item,"url"));actions.Children.Add(download);
    actions.Children.Add(Button("导入组件包…",()=>ImportComponent(item)));
   }
   actions.IsHitTestVisible=!installing&&status["busy"]?.GetValue<bool>()!=true&&status["model_busy"]?.GetValue<bool>()!=true;
   actions.Opacity=actions.IsHitTestVisible?1:0.5;
   var description=Stack(Text(S(item,"name"),16),Text(S(item,"description"),14,true),Text(detail,14,true));
   if(!installed&&!external&&string.IsNullOrWhiteSpace(S(item,"url")))description.Children.Add(Text("发布者尚未提供此组件的下载地址。",14,true));
   if(Uri.TryCreate(S(item,"url"),UriKind.Absolute,out var source)&&source.Scheme=="https")description.Children.Add(Button("下载来源",()=>Windows.System.Launcher.LaunchUriAsync(source).AsTask()));
   componentPanel.Children.Add(Card(Row(description,actions)));
  }
  if(installing){
   string caption=S(job,"phase")=="downloading"?"正在下载 "+Size(job?["done"])+" / "+Size(job?["total"]):"正在校验和安装组件…";
   componentPanel.Children.Add(Row(Text(caption,14),Button("取消",async()=>{await engine.Request("/components/cancel",new{});await Refresh(false);} )));
   componentPanel.Children.Add(new ProgressBar{Minimum=0,Maximum=Math.Max(1,job?["total"]?.GetValue<long>()??1),Value=job?["done"]?.GetValue<long>()??0,IsIndeterminate=S(job,"phase")!="downloading"});
  }
  if(job?["message"]!=null)componentPanel.Children.Add(Text(S(job,"message"),14,true));
  if(job?["error"]!=null)componentPanel.Children.Add(Text(S(job,"error"),14,true));
 }
}
