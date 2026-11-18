; Instalador de Fábrica Studio (Inno Setup 6). Lo compila el flujo de GitHub Actions:
;   ISCC.exe /DVersion=0.4.0 empaquetado\instalador.iss
; Instala para el usuario actual (sin permisos de administrador). Los datos del usuario
; (clips, ajustes, credenciales) viven en %LOCALAPPDATA%\FabricaStudio\datos y NO se borran al desinstalar.
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6C1C4E2A-5F7B-4C1D-9A3E-0F2B7D9E4A11}
AppName=Fábrica Studio
AppVersion={#Version}
AppPublisher=Fábrica Studio
DefaultDirName={localappdata}\Programs\FabricaStudio
DefaultGroupName=Fábrica Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\salida
OutputBaseFilename=FabricaStudio-Setup-{#Version}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\FabricaStudio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"
Name: "inicio"; Description: "Abrir Fábrica Studio al iniciar Windows (en segundo plano, sin abrir el navegador)"; GroupDescription: "Automatización:"; Flags: unchecked

[Files]
Source: "..\dist\FabricaStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Fábrica Studio"; Filename: "{app}\FabricaStudio.exe"; WorkingDir: "{app}"
Name: "{group}\Diagnóstico de Fábrica Studio"; Filename: "{app}\FabricaStudio.exe"; Parameters: "--diagnostico"; WorkingDir: "{app}"
Name: "{group}\Desinstalar Fábrica Studio"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Fábrica Studio"; Filename: "{app}\FabricaStudio.exe"; WorkingDir: "{app}"; Tasks: escritorio
Name: "{userstartup}\Fábrica Studio"; Filename: "{app}\FabricaStudio.exe"; Parameters: "--sin-navegador"; WorkingDir: "{app}"; Tasks: inicio; Flags: runminimized

[Run]
Filename: "{app}\FabricaStudio.exe"; Description: "Abrir Fábrica Studio ahora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM FabricaStudio.exe /F"; Flags: runhidden; RunOnceId: "CerrarFabrica"
