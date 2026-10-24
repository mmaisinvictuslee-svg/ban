@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo.
echo VillageON 실행 도우미
echo 이 창은 앱을 사용하는 동안 열어 두세요.
echo.

if not exist "%~dp0app.py" goto files_missing
if not exist "%~dp0requirements.txt" goto files_missing
if exist "%~dp0.venv\Scripts\python.exe" goto validate_venv
if exist "%~dp0.venv\" goto venv_broken

echo [1/4] 이 폴더에서 사용할 Python 환경을 만듭니다.
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto create_with_py
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto create_with_python
goto python_missing

:create_with_py
py -3 -m venv "%~dp0.venv"
if errorlevel 1 goto venv_failed
goto validate_venv

:create_with_python
python -m venv "%~dp0.venv"
if errorlevel 1 goto venv_failed
goto validate_venv

:validate_venv
"%~dp0.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto venv_broken
echo [1/4] 이 폴더의 Python 환경을 사용합니다.
"%~dp0.venv\Scripts\python.exe" -m pip --version >nul 2>&1
if not errorlevel 1 goto install_packages
"%~dp0.venv\Scripts\python.exe" -m ensurepip --upgrade
if errorlevel 1 goto pip_failed

:install_packages
echo.
echo [2/4] 필요한 패키지를 확인하고 없는 항목을 설치합니다.
echo 처음 실행할 때는 인터넷 연결이 필요하며 몇 분 걸릴 수 있습니다.
"%~dp0.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 goto packages_failed

echo.
echo [3/4] API 키 설정 상태를 확인합니다. 이 단계는 실제 API 인증 검사가 아닙니다.
if not exist "%~dp0configure_keys.py" goto keys_helper_missing
"%~dp0.venv\Scripts\python.exe" "%~dp0configure_keys.py" --check
if errorlevel 130 goto keys_cancelled
if errorlevel 2 goto keys_failed
if errorlevel 1 goto configure_api_keys
goto run_app

:configure_api_keys
echo 아직 준비되지 않은 API 키를 이 창에서 한 번 입력해 주세요.
"%~dp0.venv\Scripts\python.exe" "%~dp0configure_keys.py"
if errorlevel 130 goto keys_cancelled
if errorlevel 1 goto keys_failed
goto run_app

:keys_helper_missing
echo API 키 설정 도우미 configure_keys.py가 없어 자동 설정은 생략합니다.
echo README_KO.txt의 API 키 설정 안내를 확인해 주세요. 기존 설정으로 앱을 실행합니다.
goto run_app

:run_app
echo.
echo [4/4] 앱을 실행합니다.
echo 브라우저가 열리지 않으면 아래에 표시되는 Local URL로 접속하세요.
echo 첫 실행에서 Email 입력이 나오면 입력하지 않고 Enter를 눌러도 됩니다.
echo 종료하려면 이 창에서 Ctrl+C를 누르세요.
echo.
"%~dp0.venv\Scripts\python.exe" -m streamlit run "%~dp0app.py"
if errorlevel 1 goto run_failed
goto done

:files_missing
echo [파일 확인] app.py 또는 requirements.txt를 찾지 못했습니다.
echo ZIP 파일을 먼저 모두 압축 풀기 한 뒤, 파일들이 함께 있는 폴더에서 실행하세요.
goto failed

:python_missing
echo [Python 확인] Python 3.11 이상을 찾지 못했습니다.
echo Python 3.12 또는 3.13 설치를 권장합니다. 검증에는 3.12를 사용했습니다.
echo 설치 안내: https://www.python.org/downloads/windows/
echo 설치 후 이 창을 닫고 run_windows.bat를 다시 실행하세요.
goto failed

:venv_broken
echo [Python 환경 확인] 이 폴더의 기존 .venv를 실행할 수 없거나 버전이 낮습니다.
echo Python 3.12 또는 3.13 설치를 확인한 뒤 ZIP을 새 폴더에 풀어서 실행해 주세요.
echo 기존 폴더와 파일은 자동으로 삭제하거나 덮어쓰지 않습니다.
goto failed

:venv_failed
echo [환경 생성 실패] Python 환경을 만들지 못했습니다.
echo 위쪽 오류를 확인하고, 쓰기 가능한 새 폴더에 ZIP을 풀어 다시 실행하세요.
goto failed

:pip_failed
echo [설치 도구 확인] 이 Python 환경에서 pip를 실행할 수 없습니다.
echo Python 설치 상태를 확인하고 위쪽 오류 내용을 확인해 주세요.
goto failed

:packages_failed
echo.
echo [패키지 설치 실패] 필요한 패키지를 모두 설치하지 못했습니다.
echo 인터넷 연결과 위쪽 오류를 확인한 뒤 이 파일을 다시 실행하세요.
echo 계속 실패하면 위쪽 오류 내용을 복사해서 보내 주세요.
goto failed

:keys_failed
echo.
echo [API 키 설정 미완료] 위 안내를 확인하고 setup_api_keys.bat를 실행해 주세요.
echo 손상된 기존 설정 파일은 자동으로 덮어쓰지 않습니다. 앱 실행을 중단했습니다.
goto failed

:keys_cancelled
echo.
echo API 키 입력을 취소하여 앱 실행을 중단했습니다.
pause
endlocal
exit /b 130

:run_failed
echo.
echo 앱 실행이 중단됐습니다. 위쪽에 오류가 있으면 내용을 확인해 주세요.
goto failed

:failed
echo.
pause
endlocal
exit /b 1

:done
endlocal
exit /b 0
