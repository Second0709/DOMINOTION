#ifndef SourceDir
  #error "SourceDir must point to the PyInstaller onedir output."
#endif
#ifndef OutputDir
  #define OutputDir "output"
#endif
#ifdef BuildX86
  #define BuildArch "x86"
  #define ArchitectureMode "x86compatible"
  #define ArchitectureLabel "32 bits"
  #define AppIdentifier "{{2FA17032-E7DF-4A0D-B871-1CF924455BAB}"
#else
  #define BuildArch "x64"
  #define ArchitectureMode "x64compatible"
  #define ArchitectureLabel "64 bits"
  #define AppIdentifier "{{9D6688DB-9921-41F8-BE5C-D19275457B0D}"
#endif

[Setup]
AppId={#AppIdentifier}
AppName=DOMINOTION ({#ArchitectureLabel})
AppVersion=2.5.2
AppVerName=DOMINOTION 2.5.2 Beta ({#ArchitectureLabel})
AppPublisher=DOMINOTION
SetupIconFile=..\Icons\Dominotion_App_Icons\Dominotion.ico
DefaultDirName={localappdata}\Programs\Dominotion-{#BuildArch}
DefaultGroupName=Dominotion ({#ArchitectureLabel})
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed={#ArchitectureMode}
#ifndef BuildX86
  ArchitecturesInstallIn64BitMode=x64compatible
#endif
; Win10 build 14393 is Anniversary Update; darkdetect also requires this build.
MinVersion=10.0.14393
UninstallDisplayName=DOMINOTION ({#ArchitectureLabel})
UninstallDisplayIcon={app}\Dominotion.exe
OutputDir={#OutputDir}
OutputBaseFilename=Dominotion-Setup-2.5.2-{#BuildArch}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousGroup=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo de DOMINOTION ({#ArchitectureLabel}) en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Dominotion\DOMINOTION ({#ArchitectureLabel})"; Filename: "{app}\Dominotion.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\DOMINOTION ({#ArchitectureLabel})"; Filename: "{app}\Dominotion.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Dominotion.exe"; Description: "Iniciar DOMINOTION"; Flags: nowait postinstall skipifsilent

[Code]
var
  EliminarDatosDelUsuario: Boolean;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  CarpetaDatos: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    EliminarDatosDelUsuario :=
      SuppressibleMsgBox(
        '¿Desea eliminar también los torneos y datos guardados de DOMINOTION?' + #13#10 + #13#10 +
        'Esta acción es permanente. Seleccione No para conservarlos.',
        mbConfirmation, MB_YESNO, IDNO
      ) = IDYES;
  end
  else if (CurUninstallStep = usPostUninstall) and EliminarDatosDelUsuario then
  begin
    CarpetaDatos := ExpandConstant('{userappdata}\Dominotion');
    if DirExists(CarpetaDatos) and not DelTree(CarpetaDatos, True, True, True) then
      MsgBox(
        'No se pudieron eliminar todos los datos de esta carpeta:' + #13#10 + CarpetaDatos,
        mbError, MB_OK
      );
  end;
end;
