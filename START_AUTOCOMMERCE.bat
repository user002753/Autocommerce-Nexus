@echo off
setlocal
cd /d "%~dp0"

if exist "..\venv\Scripts\python.exe" (
  set "NEXUS_PY=..\venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
  set "NEXUS_PY=venv\Scripts\python.exe"
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    set "NEXUS_PY=py -3"
  ) else (
    set "NEXUS_PY=python"
  )
)

%NEXUS_PY% -c "import fastapi,uvicorn" >nul 2>nul
if not %errorlevel%==0 (
  echo Installing missing dependencies (FastAPI, Uvicorn)...
  %NEXUS_PY% -m pip install -r requirements.txt
)

echo.
echo ======================================================================
echo Starting AutoCommerce Nexus Universal Gateway on http://127.0.0.1:8010
echo ======================================================================
echo.

start "" http://127.0.0.1:8010
%NEXUS_PY% -m uvicorn server:app --host 127.0.0.1 --port 8010 --reload
pause
