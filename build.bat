@echo off
setlocal
title Building Wordlist-Edit-Tool Standalone Executables

REM Parse options: --clean or -c for fresh PyInstaller build
set "CLEAN_FLAG="
if "%~1"=="--clean" set "CLEAN_FLAG=--clean"
if "%~1"=="-c" set "CLEAN_FLAG=--clean"

echo =========================================================
echo [1/3] Compiling Native C Acceleration Engine...
echo =========================================================

REM Check for GCC in local w64devkit or system PATH
set "GCC_BIN=%~dp0w64devkit\bin\gcc.exe"
if not exist "%GCC_BIN%" (
    where gcc >nul 2>&1
    if %errorlevel% equ 0 (
        set "GCC_BIN=gcc"
    ) else (
        echo [WARNING] GCC not found. Skipping native C compilation, using existing fastfilter.dll if present.
        goto :PYINSTALLER_STEP
    )
)

if not exist "%~dp0dist" mkdir "%~dp0dist"

echo Compiling fastfilter.dll (C Native Acceleration)...
"%GCC_BIN%" -O3 -shared -o "%~dp0fastfilter.dll" "%~dp0fastfilter.c"
if %errorlevel% neq 0 (
    echo [WARNING] Failed to compile fastfilter.dll.
) else (
    echo fastfilter.dll compiled successfully.
)

echo Compiling fastfilter.exe (Standalone CLI Binary)...
"%GCC_BIN%" -O3 -DBUILD_CLI -o "%~dp0dist\fastfilter.exe" "%~dp0fastfilter.c"
if %errorlevel% neq 0 (
    echo [WARNING] Failed to compile fastfilter.exe CLI.
) else (
    echo fastfilter.exe standalone CLI compiled successfully.
)

:PYINSTALLER_STEP
echo.
echo =========================================================
echo [2/3] Checking PyInstaller...
echo =========================================================
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller >nul 2>&1
    if %errorlevel% neq 0 (
        py -m pip install pyinstaller >nul 2>&1
    )
) else (
    echo PyInstaller is ready (cached).
)

echo.
echo =========================================================
echo [3/3] Compiling Standalone GUI Executable...
echo =========================================================
if defined CLEAN_FLAG (
    echo Running clean PyInstaller build...
) else (
    echo Running fast incremental PyInstaller build (pass --clean for fresh build)...
)

if exist "%~dp0Wordlist-Edit-Tool.spec" (
    python -m PyInstaller %CLEAN_FLAG% -y "%~dp0Wordlist-Edit-Tool.spec"
    if %errorlevel% neq 0 (
        py -m PyInstaller %CLEAN_FLAG% -y "%~dp0Wordlist-Edit-Tool.spec"
    )
) else (
    python -m PyInstaller %CLEAN_FLAG% -y --onefile --noconsole --add-binary "fastfilter.dll;." --name "Wordlist-Edit-Tool" "%~dp0filter_app.py"
    if %errorlevel% neq 0 (
        py -m PyInstaller %CLEAN_FLAG% -y --onefile --noconsole --add-binary "fastfilter.dll;." --name "Wordlist-Edit-Tool" "%~dp0filter_app.py"
    )
)

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] PyInstaller build failed. Check error messages above.
    pause
    exit /b %errorlevel%
)

echo.
echo =========================================================
echo Build Complete!
echo =========================================================
echo Standalone GUI Executable: %~dp0dist\Wordlist-Edit-Tool.exe
if exist "%~dp0dist\fastfilter.exe" (
    echo Standalone CLI Executable: %~dp0dist\fastfilter.exe
)
echo.
explorer "%~dp0dist"
pause