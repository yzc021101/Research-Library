#define AppVersion "0.6.11"
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

[Code]
var
  ManagedFiles: TArrayOfString;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command, Expected, Relative, Target, Folder, AppFolder: String;
  ResultCode, I: Integer;
begin
  AppFolder := ExpandConstant('{app}\app');
  if CurUninstallStep = usUninstall then begin
    if FileExists(AppFolder + '\ResearchLibrary.Windows.exe') then begin
      if not Exec(AppFolder + '\ResearchLibrary.Windows.exe', '--prepare-uninstall', AppFolder,
        SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
        RaiseException('投研纵览或其 MCP 仍在使用。请关闭调用它的 AI 客户端后重新卸载。');
    end;
    LoadStringsFromFile(AppFolder + '\installed-files.txt', ManagedFiles);
    Expected := '"' + AppFolder + '\ResearchLibrary.Windows.exe" --background';
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'research_library', Command) then
      if CompareText(Command, Expected) = 0 then
        RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'research_library');
  end;
  if CurUninstallStep = usPostUninstall then begin
    { Auto-updates can add payload files not present in the original Inno log.
      Delete only the current package manifest, never wildcard user directories. }
    for I := 0 to GetArrayLength(ManagedFiles)-1 do begin
      Relative := ManagedFiles[I];
      StringChangeEx(Relative, '/', '\', True);
      if (Relative <> '') and (Pos('..', Relative) = 0) and (Pos(':', Relative) = 0)
         and (Copy(Relative,1,1) <> '\') and (Copy(Relative,1,1) <> '/') then begin
        Target := AppFolder + '\' + Relative;
        DeleteFile(Target);
        Folder := ExtractFileDir(Target);
        while (Length(Folder) > Length(AppFolder)) and RemoveDir(Folder) do
          Folder := ExtractFileDir(Folder);
      end;
    end;
    RemoveDir(AppFolder);
    { The separate library, models, original files and other startup entries stay intact. }
  end;
end;
