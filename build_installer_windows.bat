@echo off
setlocal
cd /d "%~dp0"

call build_windows.bat --no-pause
if errorlevel 1 (
  echo.
  echo La compilation de l'application a echoue.
  pause
  exit /b 1
)

set "ISCC_EXE="
where ISCC.exe >nul 2>nul
if not errorlevel 1 set "ISCC_EXE=ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC_EXE (
  echo.
  echo Inno Setup 6 est introuvable.
  echo Installez-le une fois sur le PC de compilation puis relancez ce fichier.
  echo Site officiel : https://jrsoftware.org/isinfo.php
  pause
  exit /b 1
)

if not exist "dist-installer" mkdir "dist-installer"
"%ISCC_EXE%" "CommandesCAHPP.iss"
if errorlevel 1 (
  echo.
  echo La creation de l'installeur a echoue.
  pause
  exit /b 1
)

echo.
echo Installeur termine :
echo %CD%\dist-installer\CommandesCAHPP-Setup-1.0.0-rc4.exe
echo.
echo Cet EXE remplace uniquement l'application et conserve la base,
echo les documents, le logo, les PDF et les sauvegardes.
pause
