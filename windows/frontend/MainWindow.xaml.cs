using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using System.Text.Json.Nodes;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using Windows.Storage.Pickers;
using WinRT.Interop;
namespace ResearchLibrary;
public sealed partial class MainWindow : Window {
 readonly Engine engine=new(); JsonObject settings=new(); JsonObject status=new();
 StackPanel? modelPanel; string modelFingerprint="";
 JsonObject? lastSearch; TrayIcon? tray;
 string page="home",client="Codex",query=""; bool loaded,refreshing,busy,closing;
 readonly DispatcherTimer timer=new(){Interval=TimeSpan.FromSeconds(3)};
 readonly string uiFile=Path.Combine(Engine.Root,"data","windows-ui.json"); JsonObject ui=new();
 public MainWindow(){
  InitializeComponent();ExtendsContentIntoTitleBar=true;SetTitleBar(AppTitleBar);ConfigureWindowSize();
  AdaptiveLayout.Row(PageHeader,PageTitle,PageActions,500);
  AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory,"Assets","AppIcon.ico"));
  if(File.Exists(uiFile)){try{ui=JsonNode.Parse(File.ReadAllText(uiFile))!.AsObject();}catch{}}
  ApplyTheme(ui["theme"]?.ToString()??"跟随系统");
  Navigation.DisplayModeChanged+=(_,_)=>UpdatePaneStatus();Navigation.PaneOpened+=(_,_)=>UpdatePaneStatus();Navigation.PaneClosed+=(_,_)=>UpdatePaneStatus();
  Navigation.SelectedItem=Navigation.MenuItems[0];Shell.Loaded+=Initialize;
  AppWindow.Closing+=async(_,args)=>{if(closing)return;args.Cancel=true;
   if(settings["keep_in_menu_bar"]?.GetValue<bool>()==true&&tray?.Available==true){AppWindow.Hide();return;}
   await Quit();};
  timer.Tick+=async(_,_)=>{if(!refreshing&&!busy){try{await Refresh(false);}catch(Exception ex){if(!closing)Notify("更新未完成",ex.Message,InfoBarSeverity.Warning);}}};
 }
 async void Initialize(object sender,RoutedEventArgs e){if(loaded)return;loaded=true;Navigation.IsPaneOpen=true;
  await Guard(async()=>{settings=Engine.DiskSettings();if(settings["start_service_on_launch"]?.GetValue<bool>()!=false)await engine.Start();await Refresh(true);});timer.Start();
  try{tray=new TrayIcon(WindowNative.GetWindowHandle(this),action=>DispatcherQueue.TryEnqueue(async()=>await TrayCommand(action)),()=>status.Count>0);}
  catch(Exception ex){Notify("托盘入口不可用",ex.Message,InfoBarSeverity.Warning);}
  UpdatePaneStatus();
  if(Environment.GetCommandLineArgs().Contains("--background")&&tray?.Available==true&&ui["onboarding_done"]?.GetValue<bool>()==true)AppWindow.Hide();
  if(ui["onboarding_done"]?.GetValue<bool>()!=true)await Onboarding();
  _=InitializeUpdates();
 }
 async Task Guard(Func<Task> action){if(busy)return;busy=true;try{await action();}catch(Exception ex){Notify("操作未完成",ex.Message,InfoBarSeverity.Error);}finally{busy=false;if(PageTitle.Text!=PageName(page))await Render();}}
 void Notify(string title,string message="",InfoBarSeverity severity=InfoBarSeverity.Informational){Notice.Title=title;Notice.Message=message;Notice.Severity=severity;Notice.IsOpen=true;}
 static string S(JsonNode? obj,string key,string fallback="")=>obj?[key]?.ToString()??fallback;
 Brush Brush(string name)=>(Brush)Application.Current.Resources[name];
 TextBlock Text(string text,double size=14,bool secondary=false)=>new(){Text=text,FontSize=size,TextWrapping=TextWrapping.Wrap,Style=(Style)Application.Current.Resources[secondary?"ResearchSecondaryText":"ResearchPrimaryText"],IsTextSelectionEnabled=true};
 StackPanel Stack(params UIElement[] elements){var s=new StackPanel{Spacing=10};foreach(var e in elements)s.Children.Add(e);return s;}
 Border Card(UIElement child)=>new(){Style=(Style)Application.Current.Resources["ResearchCardStyle"],Child=child};
 Grid Row(FrameworkElement description,FrameworkElement action){var r=new Grid();r.Children.Add(description);r.Children.Add(action);AdaptiveLayout.Row(r,description,action);return r;}
 static void Identify(DependencyObject control,string id,string name){Microsoft.UI.Xaml.Automation.AutomationProperties.SetAutomationId(control,id);Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(control,name);}
 public void ShowMain(){AppWindow.Show();if(AppWindow.Presenter is Microsoft.UI.Windowing.OverlappedPresenter p&&p.State==Microsoft.UI.Windowing.OverlappedPresenterState.Minimized)p.Restore();Activate();}
 async Task Quit(){if(closing)return;closing=true;timer.Stop();updateTimer.Stop();tray?.Dispose();try{await engine.CloseOwned();}finally{Close();}}
 async Task TrayCommand(string action){
  if(action=="quit"){await Quit();return;}
  if(action is "open" or "mcp" or "settings"){ShowMain();if(action!="open")await Guard(()=>Go(action));return;}
  await Guard(async()=>{if(action=="service"){if(await engine.Running())await engine.Stop();else await engine.Start();}
   else await engine.Request("/sync",new{});await Refresh(true);});
 }
 void UpdatePaneStatus(){PaneStatus.Visibility=Navigation.IsPaneOpen?Visibility.Visible:Visibility.Collapsed;PageTitle.Margin=new Thickness(Navigation.DisplayMode==NavigationViewDisplayMode.Minimal?28:0,0,0,0);}
 void ConfigureWindowSize(){
  double scale=GetDpiForWindow(WindowNative.GetWindowHandle(this))/96.0;
  var area=Microsoft.UI.Windowing.DisplayArea.GetFromWindowId(AppWindow.Id,Microsoft.UI.Windowing.DisplayAreaFallback.Primary).WorkArea;
  int width=Math.Min((int)(1280*scale),area.Width),height=Math.Min((int)(900*scale),area.Height);
  AppWindow.MoveAndResize(new Windows.Graphics.RectInt32(area.X+(area.Width-width)/2,area.Y+(area.Height-height)/2,width,height));
  if(AppWindow.Presenter is Microsoft.UI.Windowing.OverlappedPresenter presenter){presenter.PreferredMinimumWidth=(int)(460*scale);presenter.PreferredMinimumHeight=(int)(400*scale);}
 }
 [System.Runtime.InteropServices.DllImport("user32.dll")]static extern uint GetDpiForWindow(IntPtr hwnd);

 Button Button(string title,Func<Task> action,bool accent=false){var b=new Button{Content=title,HorizontalAlignment=HorizontalAlignment.Right};if(accent)b.Style=(Style)Application.Current.Resources["AccentButtonStyle"];b.Click+=async(_,_)=>await Guard(action);return b;}
 void Heading(string title,string? detail=null){Body.Children.Add(Text(title,20));if(detail!=null)Body.Children.Add(Text(detail,14,true));}
 void Note(string text)=>Body.Children.Add(Text(text,14,true));
 async Task Refresh(bool redraw){if(refreshing)return;string previous=status["sources"]?.ToJsonString()??"";refreshing=true;try{using var timeout=new CancellationTokenSource(2500);status=await engine.Request("/status",cancellationToken:timeout.Token);settings=await engine.Request("/settings",cancellationToken:timeout.Token);ServiceLabel.Text=status["busy"]?.GetValue<bool>()==true?"正在同步资料…":"服务运行中";CountLabel.Text=$"{S(status,"active_documents","0")} 份文档 · 本机存储";ServiceButton.Content="停止服务";}catch{status=new();settings=Engine.DiskSettings();ServiceLabel.Text="服务已停止";CountLabel.Text="打开服务后可检索资料";ServiceButton.Content="启动服务";}finally{refreshing=false;}UpdateSyncProgress();tray?.Update(ServiceLabel.Text);if(modelPanel!=null)UpdateModels();if(componentPanel!=null)UpdateComponents();if(updatePanel!=null)UpdateSoftware();if(redraw||(page=="home"&&previous!=(status["sources"]?.ToJsonString()??"")))await Render();}
 void UpdateSyncProgress(){
  bool active=status["busy"]?.GetValue<bool>()==true;
  SyncProgressRow.Visibility=active?Visibility.Visible:Visibility.Collapsed;
  var p=status["sync_progress"];
  string stage=S(p,"stage") switch{"ocr"=>"识别图片","embedding"=>"建立检索索引","converting"=>"转换旧版 Office","cancelled"=>"正在取消",_=>"读取资料"};
  SyncProgressText.Text=$"{stage} · {S(p,"file_index")}/{S(p,"file_total")} {S(p,"file")} {S(p,"location")}";
  CancelSyncButton.IsEnabled=active&&S(p,"stage")!="cancelled";
 }
 async void CancelSyncClick(object sender,RoutedEventArgs e)=>await Guard(async()=>{await engine.Request("/sync/cancel",new{});CancelSyncButton.IsEnabled=false;Notify("已请求取消","已完成的文档会保留，下次同步可继续。");});
 async void Navigate(NavigationView sender,NavigationViewSelectionChangedEventArgs args){page=args.IsSettingsSelected?"settings":(args.SelectedItemContainer?.Tag?.ToString()??"home");if(loaded&&!busy)await Guard(Render);}
 async Task Go(string target){if(target=="settings")Navigation.SelectedItem=Navigation.SettingsItem;else Navigation.SelectedItem=Navigation.MenuItems.OfType<NavigationViewItem>().First(x=>x.Tag?.ToString()==target);page=target;await Render();}
 static string PageName(string value)=>value switch{"sources"=>"资料来源","search"=>"检索资料","mcp"=>"MCP 接入","settings"=>"设置",_=>"概览"};
 async Task Render(){if(closing)return;modelPanel=null;componentPanel=null;updatePanel=null;Body.Children.Clear();Scroller.ChangeView(null,0,null);PageTitle.Text=PageName(page);
  switch(page){case "sources":Sources();break;case "search":Search();break;case "mcp":Mcp();break;case "settings":Settings();break;default:await Home();break;}}
 async void SyncClick(object sender,RoutedEventArgs e)=>await Guard(async()=>{await engine.Request("/sync",new{});Notify("已开始同步","完成后可在概览查看文档。",InfoBarSeverity.Success);await Refresh(true);});
 async void ServiceClick(object sender,RoutedEventArgs e)=>await Guard(async()=>{if(await engine.Running())await engine.Stop();else await engine.Start();await Refresh(true);});
 async Task Home(){
  var stats=new List<UIElement>();
  var labels=new[]{"资料文档","原文片段","来源文件夹"};var values=new[]{S(status,"active_documents","—"),S(status,"chunk_count","—"),(settings["source_folders"]?.AsArray().Count??0).ToString()};
  for(int i=0;i<3;i++){var c=Card(Stack(Text(labels[i],14,true),Text(values[i],32)));stats.Add(c);}Body.Children.Add(AdaptiveLayout.Columns(stats,180));
  Body.Children.Add(Card(Row(Stack(Text("从资料到证据",21),Text("检索本机报告、文档和表格，取回原文及准确位置。",14,true)),Button("检索资料",()=>Go("search"),true))));
  var actions=new List<UIElement>();
  actions.Add(Card(Stack(Text("连接你的 AI 工具",18),Text("为 Codex、Claude Code 等生成 MCP 配置。",14,true),Button("MCP 接入",()=>Go("mcp")))));
  var source=Card(Stack(Text("管理资料来源",18),Text("添加文件夹，资料变动时自动同步。",14,true),Button("管理文件夹",()=>Go("sources"))));actions.Add(source);Body.Children.Add(AdaptiveLayout.Columns(actions,300));
  Heading("资料库中的文档");
  if((settings["source_folders"]?.AsArray()??new()).Any(x=>x!.ToString().Contains("tests\\fixtures")))Note("当前包含合成测试资料，仅供验证功能，不能作为研究依据。");
  if(status.Count==0){Note("服务已停止。启动服务后查看文档。");return;}
  var docs=(await engine.Tool("search_documents"))["documents"]!.AsArray();
  if(docs.Count==0){Body.Children.Add(Card(Stack(Text("还没有资料",18),Text("先添加一个包含报告、文档或表格的文件夹。",14,true),Button("添加资料文件夹…",AddFolder))));return;}
  foreach(var d in docs){var doc=d!;Body.Children.Add(Card(Row(Stack(Text(S(doc,"title"),17),Text(Metadata(doc)+$" · {S(doc,"file_format","pdf").ToUpperInvariant()} · {S(doc,"unit_count",S(doc,"page_count"))} 个阅读单元",13,true)),Button("查看原文",()=>OpenOriginal(S(doc,"original_path"))))));}
  var failures=status["sources"]?.AsArray().Where(x=>S(x,"state")=="failed"&&IsCurrentSource(S(x,"path"))).ToArray()??[];
  foreach(var f in failures)Body.Children.Add(Card(Stack(Text("导入未完成",16),Text(S(f,"path"),13,true),Text(S(f,"error"),13,true))));
 }
 bool IsCurrentSource(string path){
  return (settings["source_folders"]?.AsArray()??new()).Any(folder=>{
   string relative=Path.GetRelativePath(folder!.ToString(),path);
   return !Path.IsPathRooted(relative)&&relative!=".."&&!relative.StartsWith(".."+Path.DirectorySeparatorChar);
  });
 }
 async Task OpenFolder(string path){var folder=await StorageFolder.GetFolderFromPathAsync(path);await Windows.System.Launcher.LaunchFolderAsync(folder);}
 static string Metadata(JsonNode d)=>string.Join(" · ",new[]{S(d,"institution"),S(d,"publication_date_display",S(d,"published_date")),S(d,"file_name")}.Where(x=>!string.IsNullOrWhiteSpace(x)));
 void Sources(){Note("仅访问你添加的文件夹；原文件保持只读。支持 PDF、DOC/DOCX、PPT/PPTX、XLS/XLSX、TXT、MD、RTF、CSV 和 TSV。Office 内嵌图片自动 OCR。");
  var folders=settings["source_folders"]?.AsArray()??new JsonArray();
  foreach(var f in folders){string path=f!.ToString();Body.Children.Add(Card(Row(Stack(Text(Path.GetFileName(path.TrimEnd('\\')),18),Text(path,14,true),Text(Directory.Exists(path)?"文件夹可用":"文件夹暂不可用",13,true)),Stack(Button("打开文件夹",()=>OpenFolder(path)),Button("移除",async()=>{await Save(new{source_folders=folders.Select(x=>x!.ToString()).Where(x=>x!=path).ToArray()});await Refresh(true);})))));}
  if(folders.Count==0)Body.Children.Add(Card(Stack(Text("添加你的第一个资料来源",19),Text("自动扫描子文件夹；新增、修改和移除的文件会同步更新。旧版 DOC/PPT/XLS 自动在后台转换，原文件保持不变。",14,true))));
  Body.Children.Add(Button("添加资料文件夹…",AddFolder,true));Note("移除来源后，该来源下的文档将退出检索，不会删除原文件。");
 }
 async Task AddFolder(){var picker=new FolderPicker();picker.FileTypeFilter.Add("*");InitializeWithWindow.Initialize(picker,WindowNative.GetWindowHandle(this));var folder=await picker.PickSingleFolderAsync();if(folder==null)return;
  var folders=(settings["source_folders"]?.AsArray()??new()).Select(x=>x!.ToString()).ToList();if(!folders.Contains(folder.Path,StringComparer.OrdinalIgnoreCase))folders.Add(folder.Path);
  await Save(new{source_folders=folders});Notify("已添加资料来源","正在同步新资料。",InfoBarSeverity.Success);await Refresh(true);
 }
 async Task Save(object value){settings=await engine.SaveSettings(value);}
 void Search(){
  var input=new TextBox{PlaceholderText="输入问题、公司名称或产品参数",Text=query,FontSize=16,MinHeight=40};var results=new StackPanel{Spacing=12};
  Identify(input,"SearchQuery","检索问题");
  var hint=Text($"最多返回 {S(settings,"top_k","8")} 个片段 · {ModeName(S(settings,"search_mode","hybrid"))}",13,true);
  async Task Run(){query=input.Text.Trim();if(query.Length==0)return;results.Children.Clear();results.Children.Add(new ProgressRing{IsActive=true,Width=28,Height=28});
   try{lastSearch=await engine.Tool("search_passages",new{query});ShowResults(lastSearch);}catch{results.Children.Clear();throw;}}
  void ShowResults(JsonObject data){
   results.Children.Clear();hint.Text=$"找到 {S(data,"count")} 个片段 · {ModeName(S(data,"mode"))}";
   foreach(var node in data["results"]!.AsArray()){
    var r=node!;var text=SourceContent(r);
    results.Children.Add(Card(Stack(Row(Text(S(r,"title"),18),Text(Location(r),13,true)),Text(Metadata(r),13,true),text,
     Text(r["needs_review"]?.GetValue<bool>()==true?"含图表或 OCR，请核对原图中的数字、单位和表格关系":"提取自原文",13,true),
     Row(Text($"检索得分：{S(r,"score","—")}（不代表事实可信度）",13,true),Stack(Button("查看原文与图片",()=>ReadUnit(r)),Button("打开原文件",()=>OpenOriginal(S(r,"original_path"))))))));
   }
   if(data["results"]!.AsArray().Count==0)results.Children.Add(Card(Stack(Text("没有找到相关片段",18),Text("试试更具体的关键词，或确认资料已同步完成。",14,true))));
  }
  input.TextChanged+=(_,_)=>query=input.Text;
  input.KeyDown+=async(_,e)=>{if(e.Key==Windows.System.VirtualKey.Enter)await Guard(Run);};
  Body.Children.Add(Card(Stack(Row(input,Button("检索",Run,true)),hint)));Body.Children.Add(results);
  if(lastSearch!=null)ShowResults(lastSearch);
  else if(query.Length==0){
   results.Children.Add(Text("输入中英文问题，结合页码、幻灯片、正文块、单元格或行号核对原文。",14,true));
   foreach(var item in status["search_suggestions"]?.AsArray()??new JsonArray()){
    string suggestion=item!.ToString();var button=Button(suggestion,async()=>{input.Text=suggestion;await Run();});
    button.Content=Text(suggestion,14);button.HorizontalAlignment=HorizontalAlignment.Stretch;button.HorizontalContentAlignment=HorizontalAlignment.Left;
    results.Children.Add(button);
   }
   if(S(status,"active_documents","0")=="0")results.Children.Add(Button("添加资料文件夹…",AddFolder));
  }
 }
 static string Location(JsonNode r)=>S(r["location"],"label",r["pdf_page"]!=null?$"PDF 第 {S(r,"pdf_page")} 页":"原文");
 async Task ReadUnit(JsonNode r){
  bool pdf=S(r,"file_format","pdf")=="pdf";
  var data=pdf?await engine.Tool("read_page",new{doc_id=S(r,"doc_id"),pdf_page=r["pdf_page"]!.GetValue<int>(),render=true}):await engine.Tool("read_unit",new{doc_id=S(r,"doc_id"),unit_index=r["unit_index"]!.GetValue<int>()});
  var unit=pdf?data["pages"]!.AsArray()[0]!:data["unit"]!;
  var contents=Stack();
  if(data["image_path"] is JsonNode imagePath)contents.Children.Add(new Image{Source=new BitmapImage(new Uri(imagePath.ToString())),Stretch=Stretch.Uniform});
  if(unit["review"]?.GetValue<int>()==1)contents.Children.Add(Text("OCR 或图表提取结果，请对照原图核对数字、单位和对应关系。",14,true));
  if(data["image_warning"]!=null)contents.Children.Add(Text(S(data,"image_warning"),14,true));
  foreach(var warning in data["document"]?["extraction_warnings"]?.AsArray()??new JsonArray())contents.Children.Add(Text(warning!.ToString(),14,true));
  contents.Children.Add(SourceContent(unit,true));
  var scroll=new ScrollViewer{Content=contents,MaxHeight=Math.Max(100,Shell.ActualHeight-230),HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
  var dialog=new ContentDialog{XamlRoot=Shell.XamlRoot,Title=Location(unit),Content=scroll,CloseButtonText="关闭",PrimaryButtonText="打开原文件"};
  Identify(dialog,"SourcePreview","原文与图片");
  SizeChangedEventHandler resize=(_,_)=>scroll.MaxHeight=Math.Max(100,Shell.ActualHeight-230);
  Shell.SizeChanged+=resize;
  try{if(await dialog.ShowAsync()==ContentDialogResult.Primary)await OpenOriginal(S(r,"original_path"));}finally{Shell.SizeChanged-=resize;}
 }

 async Task OpenOriginal(string path){if(string.IsNullOrWhiteSpace(path))throw new Exception("原文件已变化或不可用，请先同步资料。");var file=await StorageFile.GetFileFromPathAsync(path);await Windows.System.Launcher.LaunchFileAsync(file);}
 static string ModeName(string value)=>value switch{"keyword"=>"关键词检索","semantic"=>"语义检索",_=>"混合检索"};
 void Mcp(){
  var clients=new ComboBox{ItemsSource=new[]{"Codex","WorkBuddy","Claude Code","Cursor","VS Code","其他客户端"},SelectedItem=client,MinWidth=200};
  Identify(clients,"McpClient","选择客户端");
  var code=new TextBox{AcceptsReturn=true,Text=MCPConfiguration.Create(client),IsReadOnly=true,FontFamily=new FontFamily("Cascadia Mono"),FontSize=13,TextWrapping=TextWrapping.Wrap,MinHeight=150,MaxHeight=280};
  Identify(code,"McpConfiguration","MCP 配置文本");
  var steps=Text(MCPConfiguration.Steps(client),14,true);
  var dest=Text(MCPConfiguration.Destination(client),14,true);clients.SelectionChanged+=(_,_)=>{client=clients.SelectedItem.ToString()!;code.Text=MCPConfiguration.Create(client);dest.Text=MCPConfiguration.Destination(client);steps.Text=MCPConfiguration.Steps(client);};
  Body.Children.Add(Card(Stack(Row(Stack(Text("选择客户端",18),dest),clients),code,Button("复制完整配置",()=>Copy(MCPConfiguration.Create(client)),true))));
  Body.Children.Add(steps);
  Note("将服务条目合并到客户端原有配置，再重新加载 MCP。使用本地 STDIO，无需填写 URL 或 MCP Key。");
  Heading("验证与帮助");
  Body.Children.Add(Card(Row(Stack(Text("检查本地服务",16),Text("确认资料库服务可以响应请求。",14,true)),Button("检查连接",async()=>{var s=await engine.Tool("library_status");Notify("本地服务连接正常",$"{S(s,"active_documents")} 份文档。请在 AI 客户端中继续验证 MCP。",InfoBarSeverity.Success);} ))));
  Body.Children.Add(Card(Row(Stack(Text("在 AI 客户端验证",16),Text("复制提示词，发送到已经配置的客户端。",14,true)),Button("复制验证提示词",()=>Copy(MCPConfiguration.Verify)))));
  Body.Children.Add(Card(Row(Text("重新查看首次接入步骤",16),Button("打开引导",Onboarding))));
  Note("本地检查不能代替客户端内的 MCP 验证。使用期间请保持本应用和资料库服务运行。");
 }
 Task Copy(string value){var content=new DataPackage();content.SetText(value);Clipboard.SetContent(content);Clipboard.Flush();Notify("已复制",severity:InfoBarSeverity.Success);return Task.CompletedTask;}
 void Settings(){
  SoftwareSettings();
  Heading("通用");
  var closeBehavior=new ComboBox{ItemsSource=new[]{"最小化到托盘","直接退出"},SelectedIndex=settings["keep_in_menu_bar"]?.GetValue<bool>()==true?0:1,Width=180};
  Identify(closeBehavior,"CloseBehavior","关闭窗口时");bool updatingCloseBehavior=false;
  closeBehavior.SelectionChanged+=async(_,_)=>{
   if(updatingCloseBehavior)return;
   if(busy){updatingCloseBehavior=true;closeBehavior.SelectedIndex=settings["keep_in_menu_bar"]?.GetValue<bool>()==true?0:1;updatingCloseBehavior=false;return;}
   bool keep=closeBehavior.SelectedIndex==0;closeBehavior.IsEnabled=false;
   await Guard(async()=>{try{await Save(new{keep_in_menu_bar=keep});Notify("关闭窗口行为已保存");}
    finally{updatingCloseBehavior=true;closeBehavior.SelectedIndex=settings["keep_in_menu_bar"]?.GetValue<bool>()==true?0:1;updatingCloseBehavior=false;closeBehavior.IsEnabled=true;}});
  };
  var login=new ToggleSwitch{MinWidth=0,IsOn=LoginStartup.Enabled,OnContent="开",OffContent="关"};bool updatingLogin=false;
  Identify(login,"LoginStartup","登录 Windows 时启动");
  login.Toggled+=async(_,_)=>{if(updatingLogin)return;bool requested=login.IsOn;
   await Guard(async()=>{try{
    var confirm=new ContentDialog{XamlRoot=Shell.XamlRoot,Title=requested?"登录 Windows 时启动？":"关闭登录启动？",Content=requested?"会为当前 Windows 用户添加投研纵览登录项。登录后在托盘运行，可随时在这里关闭。":"只移除投研纵览自己的登录项，不影响其他应用。",PrimaryButtonText="确认",CloseButtonText="取消"};
    if(await confirm.ShowAsync()==ContentDialogResult.Primary)LoginStartup.Set(requested);
   }finally{updatingLogin=true;login.IsOn=LoginStartup.Enabled;updatingLogin=false;}});};
  Body.Children.Add(Card(Stack(Row(Text("关闭窗口时",16),closeBehavior),Row(Text("登录 Windows 时启动",16),login))));
  Note("最小化到托盘：关闭窗口后继续在后台运行。直接退出：关闭窗口时结束应用及其启动的服务。托盘菜单中的“退出投研纵览”始终会直接退出。");
  Heading("检索");
  var top=new NumberBox{Value=double.Parse(S(settings,"top_k","8")),Minimum=1,Maximum=20,SmallChange=1,SpinButtonPlacementMode=NumberBoxSpinButtonPlacementMode.Compact,Width=180};
  var mode=new ComboBox{ItemsSource=new[]{"混合检索","关键词检索","语义检索"},SelectedItem=ModeName(S(settings,"search_mode","hybrid")),Width=180};
  var scan=new ToggleSwitch{MinWidth=0,IsOn=settings["auto_scan"]?.GetValue<bool>()??true,OnContent="开",OffContent="关"};
  var interval=new NumberBox{Value=double.Parse(S(settings,"scan_interval","30")),Minimum=15,Maximum=600,Width=180,SpinButtonPlacementMode=NumberBoxSpinButtonPlacementMode.Compact};
  var autostart=new ToggleSwitch{MinWidth=0,IsOn=settings["start_service_on_launch"]?.GetValue<bool>()??true,OnContent="开",OffContent="关"};
  Identify(top,"TopK","返回片段数 Top K");Identify(mode,"SearchMode","检索方式");Identify(scan,"AutoScan","自动检测文件变化");Identify(interval,"ScanInterval","检查间隔 秒");Identify(autostart,"StartService","打开应用时启动服务");
  Body.Children.Add(Card(Stack(Row(Text("返回片段数（Top K）",16),top),Row(Text("检索方式",16),mode))));
  Heading("资料同步");Body.Children.Add(Card(Stack(Row(Text("自动检测文件变化",16),scan),Row(Text("检查间隔（秒）",16),interval),Row(Text("打开应用时启动服务",16),autostart))));
  Body.Children.Add(Button("保存设置",async()=>{if(double.IsNaN(top.Value)||top.Value%1!=0||double.IsNaN(interval.Value)||interval.Value%1!=0)throw new Exception("请输入范围内的整数。");await Save(new{top_k=(int)top.Value,search_mode=mode.SelectedIndex switch{1=>"keyword",2=>"semantic",_=>"hybrid"},auto_scan=scan.IsOn,scan_interval=(int)interval.Value,start_service_on_launch=autostart.IsOn});Notify("设置已保存",severity:InfoBarSeverity.Success);},true));
  Note("Top K 与检索方式同时用于 App 和 MCP；单次 MCP 调用可以另行指定。");
  Heading("外观");var theme=new ComboBox{ItemsSource=new[]{"跟随系统","浅色","深色"},SelectedItem=ui["theme"]?.ToString()??"跟随系统",Width=180};theme.SelectionChanged+=(_,_)=>{string t=theme.SelectedItem.ToString()!;ApplyTheme(t);ui["theme"]=t;PersistUI();};Body.Children.Add(Card(Row(Text("应用主题",16),theme)));
  Heading("向量模型");Note("当前模型按需载入。切换模型会重建索引；其他模型仅在你确认后下载。");
  modelPanel=new StackPanel{Spacing=12};Body.Children.Add(modelPanel);modelFingerprint="";UpdateModels();
  ComponentSettings();
  StorageSettings();
  Heading("存储");Body.Children.Add(Card(Row(Stack(Text("资料库目录",16),Text(Engine.Root,14,true)),Stack(Button("管理来源文件夹",()=>Go("sources")),Button("打开资料库文件夹",()=>OpenFolder(Engine.Root))))));
  Body.Children.Add(Button("退出投研纵览",Quit));
 }
 void UpdateModels(){
  if(modelPanel==null)return;
  string fingerprint=(status["models"]?.ToJsonString()??"")+(status["model_job"]?.ToJsonString()??"")+(status["model_busy"]?.ToString()??"");
  if(fingerprint==modelFingerprint)return;modelFingerprint=fingerprint;modelPanel.Children.Clear();
  var job=status["model_job"];string phase=S(job,"phase","idle");bool running=status["model_busy"]?.GetValue<bool>()==true||new[]{"starting","downloading","indexing","ready"}.Contains(phase);
  foreach(var node in status["models"]?.AsArray()??new JsonArray()){
   var model=node!;bool active=model["active"]?.GetValue<bool>()==true,downloaded=model["downloaded"]?.GetValue<bool>()==true;
   var button=Button(active&&downloaded?"重建索引":downloaded?"切换模型":"下载并切换",async()=>{
    var dialog=new ContentDialog{XamlRoot=Shell.XamlRoot,Title="切换向量模型",Content=$"将使用 {S(model,"name")}。"+(downloaded?"本机已有模型文件。":$"预计下载 {S(model,"download_gb")} GB。")+"切换时会重建现有资料索引。",PrimaryButtonText="继续",CloseButtonText="取消"};
    if(await dialog.ShowAsync()==ContentDialogResult.Primary){await engine.Request("/models/switch",new{model=S(model,"id")});Notify("模型任务已开始","完成前继续使用原模型。请保持应用打开。");await Refresh(false);}
   });button.IsEnabled=!running;
   modelPanel.Children.Add(Card(Row(Stack(Text(S(model,"name"),16),Text(S(model,"description"),14,true),Text(downloaded?"已下载":"按需下载",13,true)),button)));
  }
  foreach(var node in status["models"]?.AsArray()??new JsonArray()){
   if(node?["downloaded"]?.GetValue<bool>()!=true)continue;
   var model=node!;
   modelPanel.Children.Add(Row(Text("移除 "+S(model,"name")+" 本机文件",14,true),Button("移除…",async()=>{
    var dialog=new ContentDialog{XamlRoot=Shell.XamlRoot,Title="移除向量模型？",Content="文档与文本索引保留；当前模型移除后仍可使用关键词检索。",PrimaryButtonText="移除",CloseButtonText="取消"};
    if(await dialog.ShowAsync()==ContentDialogResult.Primary){await engine.Request("/models/remove",new{model=S(model,"id")});await Refresh(false);}
   })));
  }
  if(status.Count==0)modelPanel.Children.Add(Text("启动服务后可查看和切换模型。",14,true));
  if(phase!="idle"){
   string label=phase switch{"starting"=>"正在准备","downloading"=>"正在下载","indexing"=>"正在重建索引","ready"=>"正在切换","complete"=>"已完成","cancelled"=>"已取消","failed"=>"未完成",_=>phase};
   modelPanel.Children.Add(Text($"模型任务：{label} · {S(job,"completed","0")}/{S(job,"total","0")} {S(job,"error")}",14,true));
   if(running)modelPanel.Children.Add(Button("取消模型任务",async()=>{await engine.Request("/models/cancel",new{});Notify("已请求取消模型任务");await Refresh(false);}));
  }
 }
 void ApplyTheme(string theme)=>Shell.RequestedTheme=theme switch{"浅色"=>ElementTheme.Light,"深色"=>ElementTheme.Dark,_=>ElementTheme.Default};
 void PersistUI(){Directory.CreateDirectory(Path.GetDirectoryName(uiFile)!);File.WriteAllText(uiFile,ui.ToJsonString());}
 async Task Onboarding(){
  int step=0;bool actionRunning=false;
  var panel=Stack();var feedback=Text("",14,true);
  var scroll=new ScrollViewer{Content=panel,Height=Math.Max(100,Math.Min(420,Shell.ActualHeight-230)),HorizontalScrollBarVisibility=ScrollBarVisibility.Disabled};
  var dialog=new ContentDialog{XamlRoot=Shell.XamlRoot,Content=scroll,CloseButtonText="稍后配置",DefaultButton=ContentDialogButton.Primary};
  Identify(dialog,"OnboardingDialog","MCP 接入引导");
  Button Action(string title,Func<Task> action){
   var button=new Button{Content=title,HorizontalAlignment=HorizontalAlignment.Right};
   button.Click+=async(_,_)=>{
    if(actionRunning)return;actionRunning=true;button.IsEnabled=false;
    dialog.IsPrimaryButtonEnabled=false;dialog.IsSecondaryButtonEnabled=false;
    try{await action();}catch(Exception ex){feedback.Text=ex.Message;}
    finally{actionRunning=false;button.IsEnabled=true;dialog.IsPrimaryButtonEnabled=true;dialog.IsSecondaryButtonEnabled=true;}
   };return button;
  }
  void ShowStep(){
   dialog.Title=step switch{0=>"准备你的资料库",1=>"连接 AI 客户端",_=>"验证并开始使用"};
   dialog.PrimaryButtonText=step==2?"完成":"下一步";dialog.SecondaryButtonText=step>0?"上一步":"";
   panel.Children.Clear();feedback.Text="";panel.Children.Add(Text($"第 {step+1} 步，共 3 步",14,true));
   if(step==0){
    panel.Children.Add(Text("让 AI 检索本机报告、文档和表格，并取回原文及来源位置。",15,true));
    var count=Text($"{settings["source_folders"]?.AsArray().Count??0} 个文件夹",15,true);
    panel.Children.Add(Card(Stack(Row(Text("资料来源",16),count),Action("添加资料文件夹…",async()=>{await AddFolder();count.Text=$"{settings["source_folders"]?.AsArray().Count??0} 个文件夹";}))));
    panel.Children.Add(Text("可以稍后添加。原文件只读，索引和模型保存在资料库目录中。",14,true));
    panel.Children.Add(Action("启动并检查服务",async()=>{await engine.Start();await Refresh(false);feedback.Text="本地服务已准备好。";}));
   }else if(step==1){
    var clients=new ComboBox{ItemsSource=new[]{"Codex","WorkBuddy","Claude Code","Cursor","VS Code","其他客户端"},SelectedItem=client,HorizontalAlignment=HorizontalAlignment.Stretch};
    var destination=Text(MCPConfiguration.Destination(client),14,true);
    var code=new TextBox{AcceptsReturn=true,Text=MCPConfiguration.Create(client),IsReadOnly=true,TextWrapping=TextWrapping.Wrap,FontFamily=new FontFamily("Cascadia Mono"),FontSize=13,MinHeight=120,MaxHeight=200};
    var steps=Text(MCPConfiguration.Steps(client),14,true);
    clients.SelectionChanged+=(_,_)=>{client=clients.SelectedItem.ToString()!;destination.Text=MCPConfiguration.Destination(client);code.Text=MCPConfiguration.Create(client);steps.Text=MCPConfiguration.Steps(client);};
    panel.Children.Add(clients);panel.Children.Add(destination);panel.Children.Add(code);
    panel.Children.Add(Action("复制完整配置",async()=>{await Copy(MCPConfiguration.Create(client));feedback.Text="已复制。请在所选客户端中合并配置并重新加载 MCP。";}));
    panel.Children.Add(steps);
    panel.Children.Add(Text("使用本地 STDIO，无需填写 URL 或 MCP Key。",14,true));
   }else{
    panel.Children.Add(Text("先检查本地服务，再到你的 AI 客户端完成一次真实 MCP 调用。",15,true));
    panel.Children.Add(Action("检查本地连接",async()=>{await engine.Start();var result=await engine.Tool("library_status");feedback.Text=$"本地服务连接正常，当前 {S(result,"active_documents","0")} 份文档。";}));
    panel.Children.Add(Action("复制验证提示词",async()=>{await Copy(MCPConfiguration.Verify);feedback.Text="已复制。在 AI 客户端中发送此提示词，确认可以调用工具。";}));
    panel.Children.Add(Text("本地检查不能代替客户端内的 MCP 验证。原文片段会进入 AI 客户端的对话上下文。",14,true));
   }
   panel.Children.Add(feedback);scroll.ChangeView(null,0,null,true);
  }
  dialog.PrimaryButtonClick+=(_,args)=>{if(step<2){args.Cancel=true;step++;ShowStep();}};
  dialog.SecondaryButtonClick+=(_,args)=>{args.Cancel=true;if(step>0){step--;ShowStep();}};
  dialog.Closing+=(_,args)=>{if(actionRunning)args.Cancel=true;};
  SizeChangedEventHandler resize=(_,_)=>scroll.Height=Math.Max(100,Math.Min(420,Shell.ActualHeight-230));Shell.SizeChanged+=resize;
  ShowStep();ContentDialogResult result;
  try{result=await dialog.ShowAsync();}finally{Shell.SizeChanged-=resize;}
  ui["onboarding_done"]=true;PersistUI();
  if(result==ContentDialogResult.Primary)await Go("mcp");
 }
}
