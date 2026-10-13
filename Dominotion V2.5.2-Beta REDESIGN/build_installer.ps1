param(
    [ValidateSet("all", "x86", "x64")]
    [string]$Architecture = "all"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildDir = Join-Path $ProjectRoot "build"
$DistDir = Join-Path $ProjectRoot "dist"
$InstallerOutput = Join-Path $ProjectRoot "installer-output"
$SpecFile = Join-Path $ProjectRoot "Dominotion.spec"
$InnoScript = Join-Path $ProjectRoot "installer\Dominotion.iss"

$CompilerCandidates = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
$Compiler = $CompilerCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $Compiler) {
    throw "No se encontró ISCC.exe. Instale Inno Setup 6.7.3 y vuelva a ejecutar este script."
}

New-Item -ItemType Directory -Path $InstallerOutput -Force | Out-Null

function Build-Architecture {
    param(
        [ValidateSet("x86", "x64")]
        [string]$Target
    )

    if ($Target -eq "x64") {
        $BasePython = (Get-Command python.exe -ErrorAction Stop).Source
        $VenvName = ".venv-build"
        $ExpectedBits = 64
        $ExpectedMinor = 14
    }
    else {
        $BasePython = if ($env:DOMINOTION_PYTHON_X86) {
            $env:DOMINOTION_PYTHON_X86
        }
        else {
            Join-Path $env:LOCALAPPDATA "DominotionBuildTools\Python313-x86\python.exe"
        }
        $VenvName = ".venv-build-x86"
        $ExpectedBits = 32
        $ExpectedMinor = 13
        if (-not (Test-Path $BasePython)) {
            throw "No se encontró Python x86. Instale Python 3.13.13 de 32 bits o defina DOMINOTION_PYTHON_X86."
        }
    }

    $Venv = Join-Path $ProjectRoot $VenvName
    $VenvPython = Join-Path $Venv "Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) {
        & $BasePython -m venv $Venv
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno de build $VenvName." }
    }

    $RuntimeInfoJson = & $VenvPython -c "import ctypes, json, sys; print(json.dumps({'version': list(sys.version_info[:2]), 'bits': ctypes.sizeof(ctypes.c_void_p) * 8, 'platform': sys.platform}))"
    if ($LASTEXITCODE -ne 0) { throw "No se pudo comprobar $VenvName." }
    $RuntimeInfo = $RuntimeInfoJson | ConvertFrom-Json
    if ($RuntimeInfo.platform -ne "win32" -or $RuntimeInfo.bits -ne $ExpectedBits -or
        $RuntimeInfo.version[0] -ne 3 -or $RuntimeInfo.version[1] -ne $ExpectedMinor) {
        throw "$VenvName requiere Python 3.$ExpectedMinor de $ExpectedBits bits en Windows. Detectado: Python $($RuntimeInfo.version -join '.') $($RuntimeInfo.bits) bits."
    }

    & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias de $Target." }
    & $VenvPython -m unittest discover -s (Join-Path $ProjectRoot "tests")
    if ($LASTEXITCODE -ne 0) { throw "Fallaron las pruebas previas al build $Target." }

    $ArchitectureDist = Join-Path $DistDir $Target
    $ArchitectureBuild = Join-Path $BuildDir $Target
    & $VenvPython -m PyInstaller --noconfirm --clean --distpath $ArchitectureDist --workpath $ArchitectureBuild $SpecFile
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller no pudo generar el bundle $Target." }

    $CompilerArgs = @(
        "/DSourceDir=$(Join-Path $ArchitectureDist 'Dominotion')",
        "/DOutputDir=$InstallerOutput"
    )
    if ($Target -eq "x86") { $CompilerArgs += "/DBuildX86" }
    & $Compiler @CompilerArgs $InnoScript
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup no pudo generar el instalador $Target." }

    Write-Output "Instalador generado: $(Join-Path $InstallerOutput "Dominotion-Setup-2.5.2-$Target.exe")"
}

$Targets = if ($Architecture -eq "all") { @("x64", "x86") } else { @($Architecture) }
foreach ($Target in $Targets) {
    Build-Architecture -Target $Target
}
