@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" tools\release_checks.py
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m ruff check .
if errorlevel 1 goto failed
set "CAHPP_REQUIRE_GUI=1"
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
call build_installer_windows.bat --no-pause
if errorlevel 1 goto failed
".venv\Scripts\python.exe" tools\release_checks.py --manifest
if errorlevel 1 goto failed
echo.
echo Version construite et controles termines. Consultez dist-installer.
echo Testez l'installation et le lancement de l'EXE avant de le diffuser.
pause
exit /b 0

:failed
echo.
echo ECHEC : la version ne doit pas etre diffusee.
echo Un ancien installateur peut encore exister dans dist-installer.
pause
exit /b 1
