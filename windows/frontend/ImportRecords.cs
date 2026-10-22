using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;
namespace ResearchLibrary;
public sealed partial class MainWindow {
 StackPanel? importPanel;
 string importFingerprint="";
 bool failedImportsExpanded=true,readyImportsExpanded=false;
 void ImportRecords(){
  Heading("入库记录");
  importPanel=new StackPanel{Spacing=12};Body.Children.Add(importPanel);
  importFingerprint="";UpdateImportRecords();
 }
 void UpdateImportRecords(){
  if(importPanel==null)return;
  string fingerprint=(status["sources"]?.ToJsonString()??"[]")+(settings["source_folders"]?.ToJsonString()??"[]");
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
   foreach(var record in records.OrderBy(x=>Path.GetFileName(S(x,"path")),StringComparer.OrdinalIgnoreCase)){
    string path=S(record,"path");
    var title=Text(Path.GetFileName(path),15);ToolTipService.SetToolTip(title,path);
    var details=Stack(title);
    if(failed){string error=S(record,"error");if(error.Length>0)details.Children.Add(Text(error,14,true));}
    else details.Children.Add(Text(path,13,true));
    body.Children.Add(Card(Row(details,Button("打开原文件",()=>OpenOriginal(path)))));
   }
  }
  group.Expanding+=(_,_)=>{if(failed)failedImportsExpanded=true;else readyImportsExpanded=true;Populate();};
  group.Collapsed+=(_,_)=>{if(failed)failedImportsExpanded=false;else readyImportsExpanded=false;};
  group.IsExpanded=failed?failedImportsExpanded:readyImportsExpanded;
  if(group.IsExpanded)Populate();
  return group;
 }
}
