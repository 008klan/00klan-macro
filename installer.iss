; Inno Setup script for 00klan macro  (https://jrsoftware.org/isdl.php)
[Setup]
AppName=00klan macro
AppVersion=0.3.0
AppPublisher=00klan
DefaultDirName={autopf}\00klan macro
DefaultGroupName=00klan macro
OutputDir=installer_output
OutputBaseFilename=00klan-macro-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\00klan-macro.exe
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\00klan-macro.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\00klan macro"; Filename: "{app}\00klan-macro.exe"
Name: "{autodesktop}\00klan macro"; Filename: "{app}\00klan-macro.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\00klan-macro.exe"; Description: "Launch 00klan macro"; Flags: nowait postinstall skipifsilent
