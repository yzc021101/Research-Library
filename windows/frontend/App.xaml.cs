using Microsoft.UI.Xaml;
namespace ResearchLibrary;
public partial class App : Application {
 private static MainWindow? window;
 internal static void ShowExisting(){window?.DispatcherQueue.TryEnqueue(()=>window.ShowMain());}
 public App(){InitializeComponent(); UnhandledException += (_,e)=>{System.IO.Directory.CreateDirectory(Engine.Root+"\\logs");System.IO.File.AppendAllText(Engine.Root+"\\logs\\ui-errors.log",e.Exception+"\n");};}
 protected override void OnLaunched(LaunchActivatedEventArgs args){window=new MainWindow();window.Activate();}
}
