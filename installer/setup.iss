#define MyAppName "村务材料管理"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "VillageDocs"
#define MyAppExeName "村务材料管理.exe"
#ifndef MyOutputBaseFilename
#define MyOutputBaseFilename "VillageDocs-1.1.0-Setup"
#endif

[Setup]
AppId={{A906F688-7A82-4A93-A7D7-D585DC7F74C7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\VillageDocs
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=THIRD_PARTY_NOTICES.txt
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "default"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#GetEnv('HOUSEBOOK_DIST_DIR')}\*"; DestDir: "{app}"; Excludes: "resource\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\runtime\downloads\Dependencies\Microsoft Visual C++ v14 Redistributable (x64)_14.51.36247.0_Machine_X64_burn_zh-CN.exe"; DestDir: "{tmp}"; DestName: "VC_redist.x64.exe"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："

[Run]
Filename: "{tmp}\VC_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "安装 Microsoft Visual C++ 运行库..."; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
