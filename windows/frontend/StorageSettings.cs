using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
namespace ResearchLibrary;
public sealed partial class MainWindow {
 void StorageSettings(){
  Heading("引用与缓存");
  var snapshots=new ToggleSwitch{MinWidth=0,IsOn=settings["keep_snapshots"]?.GetValue<bool>()??false,OnContent="开",OffContent="关"};
  var retention=new ComboBox{ItemsSource=new[]{7,30,90,365},SelectedItem=settings["cache_retention_days"]?.GetValue<int>()??30,Width=180};
  Identify(snapshots,"KeepSnapshots","保留原文快照");Identify(retention,"CacheRetention","缓存保留天数");
  snapshots.Toggled+=async(_,_)=>await SaveControl(snapshots,new{keep_snapshots=snapshots.IsOn});
  retention.SelectionChanged+=async(_,_)=>await SaveControl(retention,new{cache_retention_days=(int)retention.SelectedItem});
  Body.Children.Add(Card(Stack(Row(Text("保留原文快照",16),snapshots),Row(Text("缓存保留天数",16),retention))));
  Note("默认关联原文件，显示真实文件名。开启快照后，同步时另存原文用于版本核对。服务每天清理过期缓存和旧索引；开启时保留当前版本快照。");
  var stats=new StackPanel{Spacing=10};var message=Text("点击刷新查看空间占用。",14,true);
  async Task ShowStats(){var data=await engine.Request("/storage/status",new{});Fill(data);}
  void Fill(JsonObject data){stats.Children.Clear();foreach(var (key,name) in new[]{("snapshots","原文快照"),("index","检索索引"),("previews","图片与预览缓存"),("conversions","格式转换缓存"),("models","向量模型"),("components","可选组件")})stats.Children.Add(Row(Text(name,16),Text(Size(data["categories"]?[key]?["bytes"]),16,true)));}
  async Task Clean(string mode){
   if(mode=="snapshots"&&snapshots.IsOn)throw new Exception("请先关闭保留原文快照，再移除全部副本。");
   var dialog=new ContentDialog{XamlRoot=Shell.XamlRoot,Title=mode=="snapshots"?"移除所有原文副本？":"清理资料库缓存？",Content="保留来源文件和当前检索文字。已清理的快照链接将失效；图片与转换缓存需要时可重新生成。",PrimaryButtonText="清理",CloseButtonText="取消"};
   if(await dialog.ShowAsync()!=ContentDialogResult.Primary)return;
   var data=await engine.Request("/storage/cleanup",new{mode});Fill(data["storage"]!.AsObject());message.Text=$"已移除 {S(data,"removed_files")} 个缓存文件，释放 {Size(data["released_bytes"])}。";
   if(data["errors"]?.AsArray().Count>0)message.Text+=" 部分内容未清理："+data["errors"]!.ToJsonString();
  }
  Heading("空间管理");Body.Children.Add(Card(Stack(stats,Row(Text("统计空间占用",16),Button("刷新",ShowStats)),Row(Text("过期快照、缓存与旧索引",16),Button("清理过期内容…",()=>Clean("expired"))),Row(Text("图片、预览和转换缓存",16),Button("清理缓存…",()=>Clean("generated"))),Row(Text("全部原文快照",16),Button("移除副本…",()=>Clean("snapshots"))),message)));
  Note("清理不会修改来源文件或移除模型。图片缓存可在下次同步或预览时重建。关闭快照后可移除已有副本；此前指向副本的链接会失效。");
 }
}
