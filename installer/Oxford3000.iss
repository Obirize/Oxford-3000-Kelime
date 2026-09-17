; Oxford 3000 Kelime - Windows kurulum paketi (Inno Setup 6)
;
;   py tools/build_setup.py        -> once exe, sonra bu kurulum derlenir
;
; Program KULLANICI klasorune kurulur (%LocalAppData%\Programs\Oxford3000),
; yonetici izni istemez. Ilerleme dosyasi (data\progress.db) exe'nin yaninda
; tutuldugu icin Program Files gibi salt okunur bir yere kurulamaz.
; Kaldirirken ilerleme SILINMEZ; kullanici isterse klasoru kendisi siler.

#define AppName      "Oxford 3000 Kelime"
#define AppVersion   "1.0.0"
#define AppPublisher "Obirize"
#define AppURL       "https://github.com/Obirize/Oxford-3000-Kelime"
#define AppExe       "Oxford3000.exe"

[Setup]
AppId={{7C1E7B2A-3F7D-4C1B-9E0F-2B5A8D3C6E41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\Programs\Oxford3000
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Oxford3000-Kurulum-{#AppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ShowLanguageDialog=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol koy"; GroupDescription: "Ek görevler:"

[Files]
Source: "..\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
; Kelime havuzu exe'nin icinde gomulu; ayrica yanina kopyalanir ki
; ileride guncellemek icin exe'yi yeniden derlemek gerekmesin.
Source: "..\data\oxford3000.json"; DestDir: "{app}\data"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "OKUBENI.md"; Flags: ignoreversion

[Dirs]
Name: "{app}\data"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} - Kaldır"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Programı şimdi başlat"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Yalnizca onbellek silinir; ilerleme (progress.db) ve yedekler KALIR.
Type: filesandordirs; Name: "{app}\data\audio"

[Messages]
WelcomeLabel2=Bu sihirbaz [name/ver] programını bilgisayarınıza kuracak.%n%nİngilizcede en sık kullanılan 3000 kelimeyi (Oxford 3000) Türkçe karşılıklarıyla ezberlemek için masaüstü programı. Tamamen çevrimdışı çalışır; yalnızca telaffuz sesi için internet kullanır.
FinishedLabel=Kurulum tamamlandı. İlerlemeniz şu klasörde tutulur:%n[name] klasörü içindeki data\progress.db%n%nProgram her açılışta otomatik yedek alır.
