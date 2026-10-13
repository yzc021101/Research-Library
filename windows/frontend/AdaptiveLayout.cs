using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
namespace ResearchLibrary;

// Reflow existing controls instead of rebuilding a page, so edits, selection and scroll survive resizing.
internal static class AdaptiveLayout {
 public static void Row(Grid grid, FrameworkElement description, FrameworkElement action, double breakpoint=520) {
  bool? stacked=null;
  void Reflow(double width) {
   if(width<=0)return;
   bool next=width<breakpoint;if(next==stacked)return;stacked=next;
   grid.ColumnDefinitions.Clear();grid.RowDefinitions.Clear();
   grid.ColumnDefinitions.Add(new(){Width=new GridLength(1,GridUnitType.Star)});
   grid.RowDefinitions.Add(new(){Height=GridLength.Auto});
   if(next)grid.RowDefinitions.Add(new(){Height=GridLength.Auto});
   else grid.ColumnDefinitions.Add(new(){Width=GridLength.Auto});
   Grid.SetRow(description,0);Grid.SetColumn(description,0);
   description.VerticalAlignment=VerticalAlignment.Center;
   Grid.SetRow(action,next?1:0);Grid.SetColumn(action,next?0:1);
   action.HorizontalAlignment=HorizontalAlignment.Right;action.VerticalAlignment=VerticalAlignment.Center;
  }
  grid.ColumnSpacing=20;grid.RowSpacing=12;
  grid.Loaded+=(_,_)=>Reflow(grid.ActualWidth);
  grid.SizeChanged+=(_,e)=>Reflow(e.NewSize.Width);
 }
 public static Grid Columns(IReadOnlyList<UIElement> items,double minimumColumnWidth) {
  var grid=new Grid{ColumnSpacing=14,RowSpacing=14};int previous=0;
  foreach(var item in items)grid.Children.Add(item);
  void Reflow(double width) {
   int count=Math.Max(1,Math.Min(items.Count,(int)((width+14)/(minimumColumnWidth+14))));
   if(count==previous)return;previous=count;
   grid.ColumnDefinitions.Clear();grid.RowDefinitions.Clear();
   for(int i=0;i<count;i++)grid.ColumnDefinitions.Add(new());
   for(int i=0;i<(items.Count+count-1)/count;i++)grid.RowDefinitions.Add(new(){Height=GridLength.Auto});
   for(int i=0;i<items.Count;i++){Grid.SetColumn((FrameworkElement)items[i],i%count);Grid.SetRow((FrameworkElement)items[i],i/count);}
  }
  Reflow(minimumColumnWidth);grid.SizeChanged+=(_,e)=>Reflow(e.NewSize.Width);return grid;
 }
}
