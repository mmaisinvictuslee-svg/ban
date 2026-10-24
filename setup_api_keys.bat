@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo.
echo VillageON API 키 설정 도우미
echo 입력값은 화면에 표시되지 않습니다.
echo.
if not exist "%~dp0configure_keys.py" goto helper_missing
if not exist "%~dp0.venv\Scripts\python.exe" goto check_py
"%~dp0.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto use_venv

:check_py
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto use_py
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto use_python
goto python_missing

:use_venv
"%~dp0.venv\Scripts\python.exe" "%~dp0configure_keys.py"
set "villageon_setup_result=%errorlevel%"
goto check_result

:use_py
py -3 "%~dp0configure_keys.py"
set "villageon_setup_result=%errorlevel%"
goto check_result

:use_python
python "%~dp0configure_keys.py"
set "villageon_setup_result=%errorlevel%"
goto check_result

:check_result
if "%villageon_setup_result%"=="130" goto cancelled
if not "%villageon_setup_result%"=="0" goto failed
echo.
echo 설정이 준비되었습니다. run_windows.bat로 앱을 실행할 수 있습니다.
pause
endlocal
exit /b 0

:helper_missing
echo configure_keys.py를 찾지 못했습니다. ZIP 파일을 모두 압축 푼 폴더에서 실행하세요.
goto failed

:python_missing
echo Python 3.11 이상이 필요합니다. Python 3.12 또는 3.13을 설치한 뒤 다시 실행하세요.
echo 설치 안내: https://www.python.org/downloads/windows/
goto failed

:cancelled
echo API 키 입력을 취소했습니다. 앱은 실행하지 않았습니다.
pause
endlocal
exit /b 130

:failed
echo.
echo API 키 설정을 완료하지 못했습니다. 위 안내를 확인해 주세요.
pause
endlocal
exit /b 1
