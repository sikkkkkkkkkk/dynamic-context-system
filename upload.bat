@echo off
echo ====================================
echo  Dynamic Context System 업로드
echo ====================================
echo.

cd /d "C:\Users\sik82\dynamic-context-system"

echo [1/3] 원격 저장소 연결 중...
git remote add origin https://github.com/sikkkkkkkkkk/dynamic-context-system.git

echo [2/3] GitHub에 푸시 중...
git push -u origin main

echo [3/3] 완료!
echo.
echo ✅ 업로드 완료!
echo 📂 리포지토리: https://github.com/sikkkkkkkkkk/dynamic-context-system
echo 🔧 다음 단계: GitHub Secrets 설정
echo.
echo API Keys 설정을 위해 API_KEYS.md 파일을 확인하세요.
echo.
pause