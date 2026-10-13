using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Text.Json.Nodes;
namespace ResearchLibrary;
public sealed partial class MainWindow {
 UIElement SourceContent(JsonNode data,bool preview=false){
  var content=Stack();
  if(data["citation_warning"] is not null)content.Children.Add(Text(S(data,"citation_warning"),14,true));
  string prose=S(data,"display_text",S(data,"text"));
  if(prose.Length>0){var text=Text(prose,14);if(!preview)text.MaxLines=10;content.Children.Add(text);}
  foreach(var item in data["tables"]?.AsArray()??new JsonArray()){
   if(item is null)continue;
   var columns=item["columns"]?.AsArray()??new JsonArray();var rows=item["rows"]?.AsArray()??new JsonArray();
   content.Children.Add(Text(S(item,"title","表格"),16));
   if(S(item,"context").Length>0)content.Children.Add(Text(S(item,"context"),13,true));
   var grid=new Grid{HorizontalAlignment=HorizontalAlignment.Left};
   Identify(grid,"SourceTable","原文表格");
   grid.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(60)});
   foreach(var col in columns){string key=S(col,"key");int longest=rows.Select(r=>S(r?["cells"]?[key],"text").Length).DefaultIfEmpty(0).Max();
    grid.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(longest>45?260:longest>16?200:140)});}
   for(int i=0;i<=rows.Count;i++)grid.RowDefinitions.Add(new RowDefinition{Height=GridLength.Auto});
   void AddCell(string value,int row,int col,bool heading,string detail=""){
    var text=Text(value.Length>0?value:" ",14);if(heading)text.FontWeight=Microsoft.UI.Text.FontWeights.SemiBold;
    var border=new Border{Child=text,Padding=new Thickness(10),BorderThickness=new Thickness(0,0,1,1),BorderBrush=Brush("DividerStrokeColorDefaultBrush"),Background=Brush(heading?"CardBackgroundFillColorSecondaryBrush":"CardBackgroundFillColorDefaultBrush")};
    if(detail.Length>0)ToolTipService.SetToolTip(border,detail);
    Grid.SetRow(border,row);Grid.SetColumn(border,col);grid.Children.Add(border);
   }
   AddCell("行",0,0,true);
   for(int c=0;c<columns.Count;c++)AddCell(S(columns[c],"label"),0,c+1,true);
   for(int r=0;r<rows.Count;r++){
    AddCell(S(rows[r],"index"),r+1,0,true);
    for(int c=0;c<columns.Count;c++){
     var cell=rows[r]?["cells"]?[S(columns[c],"key")];string value=S(cell,"text");
     if(cell?["truncated"]?.GetValue<bool>()==true)value+="\n…内容较长，请打开原文件查看完整单元格";
     AddCell(value,r+1,c+1,false,S(cell,"coordinate")+" · "+S(cell,"number_format")+" · "+S(cell,"formula"));
    }
   }
   var scroll=new ScrollViewer{Content=grid,MaxHeight=preview?460:340,HorizontalScrollMode=ScrollMode.Enabled,VerticalScrollMode=ScrollMode.Enabled,
    HorizontalScrollBarVisibility=ScrollBarVisibility.Auto,VerticalScrollBarVisibility=ScrollBarVisibility.Auto,Padding=new Thickness(0,0,16,16)};
   Identify(scroll,"SourceTableScroll","滚动原文表格");content.Children.Add(scroll);
   content.Children.Add(Text("左右滚动查看全部列；空白格保持为空。公式显示已保存的结果，未重新计算；悬停可查看公式及数字格式。",13,true));
  }
  return content;
 }
}
