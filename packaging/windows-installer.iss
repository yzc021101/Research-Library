#define AppVersion "0.6.10"
[Setup]
AppId={{4632A797-83A8-460E-A78D-5370CBA5C2F7}
AppName=投研纵览
AppVersion={#AppVersion}
AppPublisher=research_library contributors
AppPublisherURL=https://github.com/yzc021101/Research-Library
DefaultDirName={localappdata}\Programs\research_library
DefaultGroupName=投研纵览
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
WizardStyle=modern
DisableProgramGroupPage=yes
DisableDirPage=no
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=research_library-windows-x64-setup
SetupIconFile=..\windows\frontend\Assets\AppIcon.ico
UninstallDisplayIcon={app}\app\ResearchLibrary.Windows.exe
Compression=lzma2/normal
SolidCompression=yes
LZMANumBlockThreads=2
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
[Tasks]
Name: "startmenu"; Description: "创建开始菜单快捷方式"; GroupDescription: "快捷方式："
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked
[Files]
Source: "..\build\release\research_library\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\投研纵览"; Filename: "{app}\app\ResearchLibrary.Windows.exe"; WorkingDir: "{app}\app"; Tasks: startmenu
Name: "{userdesktop}\投研纵览"; Filename: "{app}\app\ResearchLibrary.Windows.exe"; WorkingDir: "{app}\app"; Tasks: desktopicon
[Run]
Filename: "{app}\app\ResearchLibrary.Windows.exe"; Description: "打开投研纵览"; Flags: nowait postinstall skipifsilent
