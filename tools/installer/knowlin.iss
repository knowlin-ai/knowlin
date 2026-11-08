; Knowlin-Setup.exe – Windows-Installer (seit 0.38.31, Wunsch beim Launch: „wirkt seriöser“ als start.bat).
; Gebaut von .github/workflows/installer.yml auf GitHub (Windows): dort liegt vorher unter build\knowlin ein eigenes,
; eingebettetes Python mit Knowlin und allen Paketen. Installiert wird nur für den angemeldeten Benutzer (keine
; Administratorrechte), unter %LOCALAPPDATA%\Programs\Knowlin. Gedächtnis, Einstellungen und Schlüssel liegen wie immer
; unter %LOCALAPPDATA%\duckpilot bzw. im Tresor von Windows – sie bleiben beim Deinstallieren erhalten.
; Herausgeber ist „Knowlin“ – kein Personenname.

#ifndef Version
  #define Version "0.0.0"
#endif
#define Quelle "build\knowlin"

[Setup]
AppId={{6F1C2B7A-4E0B-4C59-9E5B-2B1E4C0A7D31}
AppName=Knowlin
AppVersion={#Version}
AppVerName=Knowlin {#Version}
AppPublisher=Knowlin
AppPublisherURL=https://knowlin.de
AppSupportURL=https://github.com/knowlin-ai/knowlin/issues
AppUpdatesURL=https://github.com/knowlin-ai/knowlin/releases
AppCopyright=The Knowlin Authors – Apache-2.0
DefaultDirName={localappdata}\Programs\Knowlin
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Knowlin-Setup-{#Version}
SetupIconFile=knowlin.ico
UninstallDisplayIcon={app}\knowlin.ico
UninstallDisplayName=Knowlin
LicenseFile=LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
; Läuft Knowlin noch, bittet Setup es zu beenden (Restart Manager) – nur Programme, die Dateien aus diesem Ordner nutzen
CloseApplicationsFilter=*.exe,*.dll,*.pyd
VersionInfoVersion={#Version}
VersionInfoCompany=Knowlin
VersionInfoDescription=Knowlin – one mind, many bodies
VersionInfoProductName=Knowlin

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
de.Desktop=Symbol auf dem Desktop anlegen
en.Desktop=Create a desktop icon
de.Starten=Knowlin jetzt starten
en.Starten=Start Knowlin now
de.Microduck=Knowlin – direkt zur Microduck
en.Microduck=Knowlin – straight to Microduck

[Tasks]
Name: "desktop"; Description: "{cm:Desktop}"

[Files]
Source: "{#Quelle}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "knowlin.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Knowlin"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m duckpilot --app"; WorkingDir: "{app}"; IconFilename: "{app}\knowlin.ico"; Comment: "Knowlin"
Name: "{userprograms}\Knowlin - Microduck"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m duckpilot --app --modul duckpilot"; WorkingDir: "{app}"; IconFilename: "{app}\knowlin.ico"; Comment: "{cm:Microduck}"
Name: "{userdesktop}\Knowlin"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m duckpilot --app"; WorkingDir: "{app}"; IconFilename: "{app}\knowlin.ico"; Tasks: desktop

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m duckpilot --app"; WorkingDir: "{app}"; Description: "{cm:Starten}"; Flags: postinstall nowait skipifsilent
; Update aus Knowlin heraus (seit 0.38.32): still installiert – danach Knowlin von selbst wieder starten, ohne zweites
; Fenster (--neustart: das offene Fenster lädt sich selbst neu)
Filename: "{app}\python\pythonw.exe"; Parameters: "-m duckpilot --app --neustart"; WorkingDir: "{app}"; Flags: nowait; Check: WizardSilent

[UninstallDelete]
; Was Knowlin selbst nachinstalliert (Physik, Stimme) liegt im Programmordner – mit weg. Gedächtnis bleibt.
Type: filesandordirs; Name: "{app}\python"
