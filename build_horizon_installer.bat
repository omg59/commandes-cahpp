@echo off
setlocal
cd /d "%~dp0"
if /I "%~1"=="--skip-build" goto compile_installer
call horizon_windows.bat build
if errorlevel 1 exit /b 1
:compile_installer
set "CAHPP_HORIZON_ISCC="
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined CAHPP_HORIZON_ISCC set "CAHPP_HORIZON_ISCC=%%I"
for %%D in ("%ProgramFiles%\Inno Setup 6" "%ProgramFiles(x86)%\Inno Setup 6" "%LOCALAPPDATA%\Programs\Inno Setup 6" "%ProgramFiles%\Inno Setup 7" "%ProgramFiles(x86)%\Inno Setup 7" "%LOCALAPPDATA%\Programs\Inno Setup 7") do if exist "%%~D\ISCC.exe" set "CAHPP_HORIZON_ISCC=%%~D\ISCC.exe"
if not defined CAHPP_HORIZON_ISCC (
  echo Inno Setup 6 ou 7 est requis pour compiler l'installeur Horizon.
  exit /b 1
)
"%CAHPP_HORIZON_ISCC%" Horizon.iss
if errorlevel 1 exit /b 1
echo Installeur cree dans dist-installer-horizon.
