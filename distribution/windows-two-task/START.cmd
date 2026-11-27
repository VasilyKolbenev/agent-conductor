@echo off
setlocal
pushd "%~dp0" || exit /b 1
rem Runtime discovery must never install a missing interpreter.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
set "PYLAUNCHER_ALLOW_INSTALL="
set "PYLAUNCHER_ALWAYS_INSTALL="
set "py_launcher=py.exe"
:detect
"%py_launcher%" -3.12 -I -c "import sys;sys.exit(sys.version_info[:2]!=(3,12))" >nul 2>nul
if not errorlevel 1 goto use312
"%py_launcher%" -3.11 -I -c "import sys;sys.exit(sys.version_info[:2]!=(3,11))" >nul 2>nul
if not errorlevel 1 goto use311
python.exe -I -c "import sys;sys.exit(sys.version_info[:2] not in ((3,11),(3,12)))" >nul 2>nul
if errorlevel 1 goto missing
python.exe -I -B -X utf8 pilot.py %*
goto done
:use312
"%py_launcher%" -3.12 -I -B -X utf8 pilot.py %*
goto done
:use311
"%py_launcher%" -3.11 -I -B -X utf8 pilot.py %*
goto done
:missing
set "python_downloads=https://www.python.org/downloads/windows/"
echo Arachnid Studio needs Python 3.12 or 3.11 for Windows with venv and pip.
echo Get Python Install Manager from %python_downloads%
echo In a separate terminal run: pymanager install 3.12
echo After installation reopen START.cmd. RU / EN instructions: START-HERE.txt.
if not "%~1"=="" goto failed
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive ^
 -Command "exit [int]([Console]::IsInputRedirected -or [Console]::IsOutputRedirected)" 2>nul
if errorlevel 1 goto failed
:options
rem Use the Python Software Foundation MSIX package aliases, never a manager from the ZIP or PATH.
set "choices=ORQH"
set "manager_dir="
set "family_root=%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.PythonManager"
for %%S in (3847v3x7pw1km qbz5n2kfra8p0) do (
    if exist "%family_root%_%%S\pymanager.exe" set "manager_dir=%family_root%_%%S"
)
if defined manager_dir (
    echo [I] Download and install Python 3.12 for this Windows user with Python Install Manager.
    set "choices=ORQHI"
)
echo [H] Read the local setup guide / RU / EN.
"%SystemRoot%\System32\choice.exe" /C %choices% /N /M "[O] Open python.org, [R] retry, [Q] quit: "
if errorlevel 6 goto failed
if errorlevel 5 goto install
if errorlevel 4 goto help
if errorlevel 3 goto failed
if errorlevel 2 goto retry
if not errorlevel 1 goto failed
start "" "%python_downloads%"
goto options
:help
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive ^
 -Command "Get-Content -LiteralPath 'START-HERE.txt' -Encoding UTF8"
goto options
:install
if not defined manager_dir goto failed
"%manager_dir%\pymanager.exe" install 3.12
if not errorlevel 1 goto retry
echo Installation did not complete. You can retry the check or quit.
goto options
:retry
if defined manager_dir if exist "%manager_dir%\py.exe" set "py_launcher=%manager_dir%\py.exe"
goto detect
:failed
popd
exit /b 1
:done
set "pilot_status=%errorlevel%"
popd
exit /b %pilot_status%
