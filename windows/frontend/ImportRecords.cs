using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;
namespace ResearchLibrary;
public sealed partial class MainWindow {
 StackPanel? importPanel;
 string importFingerprint="";
 bool failedImportsExpanded=true,readyImportsExpanded=false;
 async Task RetryImports(string? path=null){
  if(busy||status["busy"]?.GetValue<bool>()==true)return;
  await Guard(async()=>{
   var result=await engine.Request("/imports/retry",path==null?new{}:(object)new{path});
   Notify(result["accepted"]?.GetValue<bool>()==true?"已开始重试失败文件":"请等待当前任务完成后重试");
   importFingerprint="";await Refresh(false);
  });
 }
 void ImportRecords(){
  Heading("入库记录");
  importPanel=new StackPanel{Spacing=12};Body.Children.Add(importPanel);
  importFingerprint="";UpdateImportRecords();
 }
 void UpdateImportRecords(){
  if(importPanel==null)return;
  string fingerprint=(status["sources"]?.ToJsonString()??"[]")+(settings["source_folders"]?.ToJsonString()??"[]")+S(status,"busy");
  if(fingerprint==importFingerprint)return;
  importFingerprint=fingerprint;importPanel.Children.Clear();
  var records=(status["sources"]?.AsArray()??new()).Where(x=>x!=null&&IsCurrentSource(S(x,"path"))).ToArray();
  importPanel.Children.Add(ImportGroup(records.Where(x=>S(x,"state")=="failed").ToArray(),true));
  importPanel.Children.Add(ImportGroup(records.Where(x=>S(x,"state")=="ready").ToArray(),false));
 }
 Expander ImportGroup(JsonNode?[] records,bool failed){
  var heading=Text($"{(failed?"导入失败":"已入库")} · {records.Length} 份",16);
  heading.IsTextSelectionEnabled=false;
  var header=new StackPanel{Orientation=Orientation.Horizontal,Spacing=10};
  var icon=new FontIcon{Glyph=failed?"\uE783":"\uE73E",FontSize=18};
  if(failed&&records.Length>0){var red=new SolidColorBrush(Microsoft.UI.Colors.IndianRed);icon.Foreground=red;heading.Foreground=red;}
  header.Children.Add(icon);header.Children.Add(heading);
  var body=new StackPanel{Spacing=12};
  var group=new Expander{Header=header,Content=body,HorizontalAlignment=HorizontalAlignment.Stretch,HorizontalContentAlignment=HorizontalAlignment.Stretch};
  Identify(group,failed?"FailedImports":"ReadyImports",$"{(failed?"导入失败":"已入库")}，{records.Length} 份");
  bool populated=false;
  void Populate(){
   if(populated)return;populated=true;
   if(records.Length==0){body.Children.Add(Text(failed?"没有失败的导入记录":"暂无已入库文档",14,true));return;}
   if(failed){var retryAll=Button("重试所有失败文件",()=>RetryImports());Identify(retryAll,"RetryAllImports","重试所有失败文件");retryAll.IsEnabled=status["busy"]?.GetValue<bool>()!=true;body.Children.Add(Row(Text("重新导入失败的文件",14,true),retryAll));}
   foreach(var record in records.OrderBy(x=>Path.GetFileName(S(x,"path")),StringComparer.OrdinalIgnoreCase)){
    string path=S(record,"path");
    var title=Text(Path.GetFileName(path),15);ToolTipService.SetToolTip(title,path);
    var details=Stack(title);
    string error=S(record,"error");
    if(error.Length>0)details.Children.Add(Text(error,14,true));
    else details.Children.Add(Text(path,13,true));
    var actions=new StackPanel{Orientation=Orientation.Horizontal,Spacing=8};
    if(failed){var retry=Button("重试",()=>RetryImports(path));Identify(retry,"RetryImport","重试 "+Path.GetFileName(path));retry.IsEnabled=status["busy"]?.GetValue<bool>()!=true;actions.Children.Add(retry);}
    actions.Children.Add(Button("打开原文件",()=>OpenOriginal(path)));
    body.Children.Add(Card(Row(details,actions)));
   }
  }
  group.Expanding+=(_,_)=>{if(failed)failedImportsExpanded=true;else readyImportsExpanded=true;Populate();};
  group.Collapsed+=(_,_)=>{if(failed)failedImportsExpanded=false;else readyImportsExpanded=false;};
  group.IsExpanded=failed?failedImportsExpanded:readyImportsExpanded;
  if(group.IsExpanded)Populate();
  return group;
 }
}
