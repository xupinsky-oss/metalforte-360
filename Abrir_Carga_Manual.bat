@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m streamlit run carga_manual_app.py
) else if exist "..\METALFORTE_360_CLOUD\.venv\Scripts\python.exe" (
  "..\METALFORTE_360_CLOUD\.venv\Scripts\python.exe" -m streamlit run carga_manual_app.py
) else (
  py -m streamlit run carga_manual_app.py
)

if errorlevel 1 (
  echo.
  echo Nao foi possivel abrir o painel de carga.
  echo Verifique se o ambiente Python do METALFORTE 360 esta instalado.
  pause
)
