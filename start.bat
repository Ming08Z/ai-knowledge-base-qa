@echo off
setlocal
set "CONDA_EXE=%ProgramData%\anaconda3\Scripts\conda.exe"
if not exist "%CONDA_EXE%" (
  echo Cannot find Conda: %CONDA_EXE%
  exit /b 1
)
pushd "%~dp0"
if not exist ".env" (
  echo First run: initialize the MySQL database.
  "%CONDA_EXE%" run --no-capture-output -n a1 python backend\setup_mysql.py
  if errorlevel 1 exit /b 1
)
"%CONDA_EXE%" run -n a1 npm run build
if errorlevel 1 exit /b 1
"%CONDA_EXE%" run -n a1 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
popd
