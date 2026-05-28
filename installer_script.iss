; Script atualizado para Inno Setup
[Setup]
; AppId único (identifica o app no Windows). Gere um novo em Tools -> Generate GUID se desejar.
AppId={{A1B2C3D4-E5F6-4789-ABCD-EF0123456789}
AppName=Pixel Patrol
AppVersion=1.0
AppPublisher=Erick de Oliveira Bessa Xavier
DefaultDirName={autopf}\Pixel Patrol
DisableProgramGroupPage=yes
; Ícone do desinstalador no Painel de Controle
UninstallDisplayIcon={app}\Pixel_Patrol.exe
SetupIconFile=game\assets\icons\ship_icon_instalador.ico
OutputDir=Output
OutputBaseFilename=setup_pixel_patrol
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Permite instalar sem admin se o usuário escolher uma pasta pessoal (como Downloads ou Desktop)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; O executável principal gerado pelo PyInstaller (deve estar na pasta dist)
Source: "dist\Pixel_Patrol.exe"; DestDir: "{app}"; Flags: ignoreversion
; Os assets recursivamente (imagens, sons, fontes)
Source: "game\assets\*"; DestDir: "{app}\game\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Pixel Patrol"; Filename: "{app}\Pixel_Patrol.exe"; IconFilename: "{app}\game\assets\icons\ship_icon_instalador.ico"
Name: "{autodesktop}\Pixel Patrol"; Filename: "{app}\Pixel_Patrol.exe"; IconFilename: "{app}\game\assets\icons\ship_icon_instalador.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Pixel_Patrol.exe"; Description: "{cm:LaunchProgram,Pixel Patrol}"; Flags: nowait postinstall skipifdoesntexist
