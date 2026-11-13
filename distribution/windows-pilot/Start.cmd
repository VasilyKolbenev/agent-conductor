@echo off
setlocal
pushd "%~dp0" || exit /b 1
where py.exe >nul 2>nul
if errorlevel 1 goto usepython
py -3.12 -I -c "import sys;sys.exit(sys.version_info[:2]!=(3,12))" >nul 2>nul
if not errorlevel 1 goto use312
py -3.11 -I -c "import sys;sys.exit(sys.version_info[:2]!=(3,11))" >nul 2>nul
if not errorlevel 1 goto use311
:usepython
where python.exe >nul 2>nul
if errorlevel 1 goto missing
python.exe -I -c "import sys;sys.exit(sys.version_info[:2] not in ((3,11),(3,12)))" >nul 2>nul
if errorlevel 1 goto missing
python.exe -I -B -X utf8 pilot.py %*
goto done
:use312
py -3.12 -I -B -X utf8 pilot.py %*
goto done
:use311
py -3.11 -I -B -X utf8 pilot.py %*
goto done
:missing
echo Install Python 3.12 or 3.11 for Windows with venv and pip. See START-HERE.txt.
popd
exit /b 1
:done
set "pilot_status=%errorlevel%"
popd
exit /b %pilot_status%
