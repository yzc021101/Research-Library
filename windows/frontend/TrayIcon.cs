using System.Runtime.InteropServices;
namespace ResearchLibrary;

// Owned by the UI thread; no hooks or changes to other applications.
internal sealed class TrayIcon : IDisposable {
 const uint Callback=0x8000+73;
 readonly IntPtr hwnd; IntPtr icon; readonly SubclassProc procedure;
 readonly Action<string> command; readonly Func<bool> serviceRunning;
 readonly uint taskbarCreated=RegisterWindowMessage("TaskbarCreated");
 NotifyIconData data; bool disposed;
 public bool Available {get;private set;}
 public TrayIcon(IntPtr window,Action<string> command,Func<bool> serviceRunning){
  hwnd=window;this.command=command;this.serviceRunning=serviceRunning;procedure=WindowProcedure;
  icon=LoadTrayImage();
  data=new(){cbSize=(uint)Marshal.SizeOf<NotifyIconData>(),hWnd=hwnd,uID=1,uFlags=1|2|4|128,uCallbackMessage=Callback,hIcon=icon,szTip="投研纵览",szInfo="",szInfoTitle=""};
  if(icon==IntPtr.Zero||!SetWindowSubclass(hwnd,procedure,73,0)){if(icon!=IntPtr.Zero)DestroyIcon(icon);throw new IOException("无法创建系统托盘入口，窗口将保持可见。");}
  Add();
 }
 IntPtr LoadTrayImage(){
  bool light=false;try{using var key=Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");light=Convert.ToInt32(key?.GetValue("SystemUsesLightTheme",0))==1;}catch{}
  int size=GetSystemMetricsForDpi(49,GetDpiForWindow(hwnd));if(size<16)size=16;
  return LoadImage(IntPtr.Zero,Path.Combine(AppContext.BaseDirectory,"Assets",light?"TrayLight.ico":"TrayDark.ico"),1,size,size,0x10);
 }
 void RefreshImage(){var next=LoadTrayImage();if(next==IntPtr.Zero)return;var old=icon;icon=next;data.hIcon=next;Shell_NotifyIcon(1,ref data);if(old!=IntPtr.Zero)DestroyIcon(old);}
 void Add(){Available=Shell_NotifyIcon(0,ref data);if(Available){data.uVersion=4;Shell_NotifyIcon(4,ref data);}}
 public void Update(string status){data.szTip=("投研纵览 · "+status);if(data.szTip.Length>127)data.szTip=data.szTip[..127];if(!Available)Add();else Available=Shell_NotifyIcon(1,ref data);}
 IntPtr WindowProcedure(IntPtr h,uint message,nuint w,nint l,nuint id,nuint reference){
  if(message is 0x001A or 0x031A or 0x02E0)RefreshImage(); // settings, theme, DPI
  if(message==taskbarCreated){Add();if(!Available)command("open");}
  if(message==Callback){
   uint notification=(uint)((long)l&0xffff);
   if(notification is 0x400 or 0x401 or 0x203)command("open"); // select, keyboard select, double click
   else if(notification==0x7b)Menu();
   return IntPtr.Zero;
  }
  return DefSubclassProc(h,message,w,l);
 }
 void Menu(){
  IntPtr menu=CreatePopupMenu();if(menu==IntPtr.Zero)return;
  try{
   AppendMenu(menu,0,1,"打开投研纵览");AppendMenu(menu,0,2,"MCP 接入");AppendMenu(menu,0,3,"设置");
   AppendMenu(menu,0x800,0,null);AppendMenu(menu,0,4,serviceRunning()?"停止服务":"启动服务");AppendMenu(menu,0,5,"同步资料");
   AppendMenu(menu,0x800,0,null);AppendMenu(menu,0,6,"退出投研纵览");
   GetCursorPos(out var position);SetForegroundWindow(hwnd);
   uint selected=TrackPopupMenuEx(menu,0x100|0x2,position.X,position.Y,hwnd,IntPtr.Zero);
   PostMessage(hwnd,0,0,0);
   if(selected!=0)command(selected switch{1=>"open",2=>"mcp",3=>"settings",4=>"service",5=>"sync",_=>"quit"});
  }finally{DestroyMenu(menu);}
 }
 public void Dispose(){if(disposed)return;disposed=true;Shell_NotifyIcon(2,ref data);RemoveWindowSubclass(hwnd,procedure,73);DestroyIcon(icon);Available=false;}
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]struct NotifyIconData {
  public uint cbSize;public IntPtr hWnd;public uint uID,uFlags,uCallbackMessage;public IntPtr hIcon;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=128)]public string szTip;
  public uint dwState,dwStateMask;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)]public string szInfo;
  public uint uVersion;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=64)]public string szInfoTitle;
  public uint dwInfoFlags;public Guid guidItem;public IntPtr hBalloonIcon;
 }
 [StructLayout(LayoutKind.Sequential)]struct Point {public int X,Y;}
 [UnmanagedFunctionPointer(CallingConvention.Winapi)]delegate IntPtr SubclassProc(IntPtr h,uint m,nuint w,nint l,nuint id,nuint reference);
 [DllImport("user32.dll")]static extern uint GetDpiForWindow(IntPtr h);
 [DllImport("user32.dll")]static extern int GetSystemMetricsForDpi(int index,uint dpi);
 [DllImport("shell32.dll",CharSet=CharSet.Unicode)]static extern bool Shell_NotifyIcon(uint message,ref NotifyIconData data);
 [DllImport("comctl32.dll")]static extern bool SetWindowSubclass(IntPtr h,SubclassProc proc,nuint id,nuint data);
 [DllImport("comctl32.dll")]static extern bool RemoveWindowSubclass(IntPtr h,SubclassProc proc,nuint id);
 [DllImport("comctl32.dll")]static extern IntPtr DefSubclassProc(IntPtr h,uint message,nuint w,nint l);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadImage(IntPtr instance,string name,uint type,int cx,int cy,uint flags);
 [DllImport("user32.dll")]static extern bool DestroyIcon(IntPtr icon);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)]static extern uint RegisterWindowMessage(string message);
 [DllImport("user32.dll")]static extern IntPtr CreatePopupMenu();
 [DllImport("user32.dll",CharSet=CharSet.Unicode)]static extern bool AppendMenu(IntPtr menu,uint flags,nuint id,string? text);
 [DllImport("user32.dll")]static extern bool DestroyMenu(IntPtr menu);
 [DllImport("user32.dll")]static extern bool GetCursorPos(out Point point);
 [DllImport("user32.dll")]static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")]static extern uint TrackPopupMenuEx(IntPtr menu,uint flags,int x,int y,IntPtr window,IntPtr parameters);
 [DllImport("user32.dll")]static extern bool PostMessage(IntPtr h,uint message,nuint w,nint l);
}
