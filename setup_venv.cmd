@echo off
chcp 65001 >nul
rem 폴더 이동/이름 변경 후 venv 재생성 스크립트 (스크립트 위치 기준으로 동작)
cd /d %~dp0

echo [1/4] 기존 .venv 삭제...
if exist .venv rmdir /s /q .venv

echo [2/4] venv 생성 + 의존성 설치 (pip 캐시가 있어 다운로드는 거의 없음)...
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [3/4] mecab DLL 복사 (g2pk용)...
copy /y "C:\mecab\bin\libmecab.dll" ".venv\Lib\site-packages\libmecab.dll" >nul

echo [4/4] 검증 (테스트 43개)...
.venv\Scripts\python.exe -m pytest tests -q
if errorlevel 1 goto :fail

echo.
echo 완료! 서버 실행:  .venv\Scripts\uvicorn.exe app.main:app --port 8000
pause
exit /b 0

:fail
echo.
echo 실패 — 위 오류 메시지를 확인하세요.
pause
exit /b 1
