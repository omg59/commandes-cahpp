@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python n'est pas installe ou le lanceur "py" est introuvable.
  echo Installer Python 3.12 64 bits puis relancer ce fichier.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

if exist "build" rmdir /s /q "build"
if exist "dist\CommandesCAHPP-portable" rmdir /s /q "dist\CommandesCAHPP-portable"

".venv\Scripts\python.exe" -m PyInstaller CommandesCAHPP.spec --noconfirm --clean
if errorlevel 1 exit /b 1

if not exist "dist\CommandesCAHPP-portable\data" mkdir "dist\CommandesCAHPP-portable\data"
if not exist "dist\CommandesCAHPP-portable\exports" mkdir "dist\CommandesCAHPP-portable\exports"

if exist "data\commandes_cahpp.sqlite3" (
  copy /y "data\commandes_cahpp.sqlite3" "dist\CommandesCAHPP-portable\data\commandes_cahpp.sqlite3" >nul
)

echo.
echo Compilation terminee :
echo %CD%\dist\CommandesCAHPP-portable
pause

