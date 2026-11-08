@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv-horizon-py315\Scripts\python.exe" (
  py -3.15-64 -m venv .venv-horizon-py315
  if errorlevel 1 goto failed
)
".venv-horizon-py315\Scripts\python.exe" -c "import PySide6.QtWidgets,openpyxl,reportlab,PIL" >nul 2>&1
if errorlevel 1 (
  ".venv-horizon-py315\Scripts\python.exe" -m pip install -r requirements-horizon.txt
  if errorlevel 1 goto failed
)
if /I "%~1"=="build" goto build

".venv-horizon-py315\Scripts\python.exe" main_horizon.py
if errorlevel 1 goto failed
exit /b 0

:build
".venv-horizon-py315\Scripts\python.exe" -m pip install -r requirements-horizon.txt -r requirements-dev.txt
if errorlevel 1 goto failed
".venv-horizon-py315\Scripts\python.exe" -m ruff check .
if errorlevel 1 goto failed
".venv-horizon-py315\Scripts\python.exe" tools\release_checks.py
if errorlevel 1 goto failed
set "CAHPP_REQUIRE_HORIZON_GUI=1"
".venv-horizon-py315\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
".venv-horizon-py315\Scripts\python.exe" -m PyInstaller Horizon.spec --noconfirm --clean
if errorlevel 1 goto failed
echo.
echo Horizon construit dans dist\CommandesCAHPP-Horizon-portable.
echo Conservez le dossier _internal avec l'EXE.
pause
exit /b 0

:failed
echo.
echo ECHEC : consultez les messages ci-dessus.
pause
exit /b 1
