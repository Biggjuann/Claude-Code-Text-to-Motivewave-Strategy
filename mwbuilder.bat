@echo off
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if "%1"=="" goto help
if "%1"=="build" goto build
if "%1"=="deploy" goto deploy
if "%1"=="all" goto all
if "%1"=="help" goto help
goto help

:build
echo ============================================
echo Building MotiveWave Study...
echo ============================================
call gradlew.bat build
if %ERRORLEVEL% equ 0 (
    echo.
    echo Build successful!
    dir /b build\libs\*.jar 2>nul
)
goto end

:deploy
echo ============================================
echo Deploying to MotiveWave...
echo ============================================
call gradlew.bat deploy
if %ERRORLEVEL% equ 0 (
    echo.
    echo Deploy successful!
    echo Restart MotiveWave or reload extensions.
)
goto end

:all
echo ============================================
echo Running full pipeline...
echo ============================================
call gradlew.bat build
if %ERRORLEVEL% neq 0 goto end
echo.
call gradlew.bat deploy
if %ERRORLEVEL% equ 0 (
    echo.
    echo ============================================
    echo Pipeline complete!
    echo ============================================
)
goto end

:help
echo.
echo mwbuilder - MotiveWave Study Builder
echo.
echo Usage: mwbuilder [command]
echo.
echo Commands:
echo   build    - Compile and create JAR
echo   deploy   - Deploy JAR to MotiveWave Extensions
echo   all      - Full pipeline: build + deploy
echo   help     - Show this help message
echo.
goto end

:end
endlocal
