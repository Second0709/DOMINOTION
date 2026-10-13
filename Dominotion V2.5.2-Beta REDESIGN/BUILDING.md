# Construir el instalador de DOMINOTION

Hay dos builds nativos: Windows x64 y Windows x86. Cada uno usa PyInstaller
`onedir` e Inno Setup por usuario. En equipos con Windows de 32 bits se debe
usar el instalador x86 aunque el procesador soporte x64; el instalador x64 es
solo para Windows de 64 bits. Ambos pueden instalarse en Windows 10 versión
1607 (build 14393, Anniversary Update) o posterior y en Windows 11. Los
torneos se guardan en `%APPDATA%\Dominotion`, fuera de la carpeta de instalación.

## Requisitos

- Para generar ambos instaladores, Windows x64 con Python 3.14 x64 y Python
  3.13.13 x86 instalados, ambos con Tcl/Tk habilitado.
- Python 3.13.13 x86 puede instalarse por usuario desde el instalador oficial de
  32 bits de Python. El script admite indicar su ruta con
  `DOMINOTION_PYTHON_X86`.
- En el equipo destino: Windows 10 build 14393 o posterior (x86 o x64 según el
  instalador elegido). Las versiones anteriores a Anniversary Update no son
  compatibles.
- Inno Setup 6.7.3 instalado para el usuario actual o disponible en `PATH`.
- Acceso a PyPI durante el primer build para crear `.venv-build` e instalar las
  versiones fijadas en `requirements-build.txt`.

## Build

Desde PowerShell, en la carpeta del proyecto:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\build_installer.ps1
```

El cambio de política solo dura en esa ventana de PowerShell; no altera la
configuración permanente del equipo.

El script crea entornos de build separados para las arquitecturas y no cambia
las instalaciones globales de Python.

```powershell
.\build_installer.ps1                 # x64 y x86
.\build_installer.ps1 -Architecture x64
.\build_installer.ps1 -Architecture x86
```

Los bundles quedan en `dist\x64\Dominotion` y `dist\x86\Dominotion`. Los
instaladores resultantes son `installer-output\Dominotion-Setup-2.5.2-x64.exe`
y `installer-output\Dominotion-Setup-2.5.2-x86.exe`. El build x86 usa
`.venv-build-x86` (Python 3.13 x86); el x64 usa `.venv-build` (Python 3.14 x64).
Instalar ambas variantes en un mismo perfil comparte `%APPDATA%\Dominotion`;
usa una sola variante por equipo y no ejecutes ambas a la vez.

## Actualizar

Mantener los AppId específicos de cada arquitectura en
`installer\Dominotion.iss` entre versiones para que cada build actualice su
propia instalación. Los accesos directos y carpetas de instalación se
distinguen entre x86 y x64. La base de datos está fuera de `{app}` y no se
elimina durante una actualización.

## Desinstalar

El desinstalador siempre elimina los archivos de programa. Pregunta por separado
si también debe eliminar `%APPDATA%\Dominotion`; responder No conserva los datos.
En una desinstalación silenciosa, la respuesta predeterminada es No y se conservan
los datos. La confirmación de limpieza no se ejecuta como parte de una actualización normal.
Las rutas personalizadas por `DOMINOTION_DATA_DIR` o `DOMINOTION_DB_PATH` están
fuera de esa carpeta y no las elimina el desinstalador.

## Recursos y distribución

PyInstaller incluye los archivos de `Fonts`, incluida la licencia OFL, en el
bundle para que los PDF usen Glacial Indifference. El instalador no tiene firma
Authenticode; Windows puede mostrar una advertencia de editor desconocido hasta
que el ejecutable se firme con un certificado del distribuidor.
