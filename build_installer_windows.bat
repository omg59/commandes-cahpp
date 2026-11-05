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
if defined INNO_SETUP_ISCC if exist "%INNO_SETUP_ISCC%" set "ISCC_EXE=%INNO_SETUP_ISCC%"
where ISCC.exe >nul 2>nul
if not errorlevel 1 if not defined ISCC_EXE set "ISCC_EXE=ISCC.exe"
if not defined ISCC_EXE if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if not defined ISCC_EXE if exist "%LOCALAPPDATA%\Inno Setup 7\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Inno Setup 7\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC_EXE if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%LOCALAPPDATA%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Microsoft\WinGet\Links\ISCC.exe"
if not defined ISCC_EXE if exist "%USERPROFILE%\scoop\apps\innosetup\current\ISCC.exe" set "ISCC_EXE=%USERPROFILE%\scoop\apps\innosetup\current\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_EXE if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC_EXE (
  for %%K in (
    "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"
    "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1"
    "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    "HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    "HKLM\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
  ) do (
    for /f "tokens=2,*" %%A in ('reg query "%%~K" /v InstallLocation 2^>nul ^| find /i "InstallLocation"') do (
      if exist "%%B\ISCC.exe" set "ISCC_EXE=%%B\ISCC.exe"
    )
  )
)

if not defined ISCC_EXE (
  echo.
  echo Inno Setup 6 ou 7 est introuvable.
  echo Installez-le une fois sur le PC de compilation puis relancez ce fichier.
  echo.
  echo Si Inno Setup est installe dans un dossier personnalise, lancez :
  echo set "INNO_SETUP_ISCC=C:\chemin\vers\ISCC.exe"
  echo build_installer_windows.bat
  echo Site officiel : https://jrsoftware.org/isinfo.php
  pause
  exit /b 1
)

echo.
echo Inno Setup detecte :
echo %ISCC_EXE%

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
echo %CD%\dist-installer\CommandesCAHPP-Setup-1.5.1.exe
echo.
echo Cet EXE remplace uniquement l'application et conserve la base,
echo les documents, le logo, les PDF et les sauvegardes.
if /I "%~1"=="--no-pause" exit /b 0
pause
