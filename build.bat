@echo off
setlocal
title Building WordLengthFilter Standalone Executables

echo =========================================================
echo [1/4] Compiling Native C Acceleration Engine...
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
echo [2/4] Ensuring PyInstaller is ready...
echo =========================================================
python -m pip install --upgrade pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    py -m pip install --upgrade pyinstaller >nul 2>&1
)

echo.
echo =========================================================
echo [3/4] Compiling Standalone GUI Executable...
echo =========================================================
if exist "%~dp0WordLengthFilter.spec" (
    python -m PyInstaller --clean -y "%~dp0WordLengthFilter.spec"
    if %errorlevel% neq 0 (
        py -m PyInstaller --clean -y "%~dp0WordLengthFilter.spec"
    )
) else (
    python -m PyInstaller --clean -y --onefile --noconsole --add-binary "fastfilter.dll;." --name "WordLengthFilter" "%~dp0filter_app.py"
    if %errorlevel% neq 0 (
        py -m PyInstaller --clean -y --onefile --noconsole --add-binary "fastfilter.dll;." --name "WordLengthFilter" "%~dp0filter_app.py"
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
echo [4/4] Build Complete!
echo =========================================================
echo Standalone GUI Executable: %~dp0dist\WordLengthFilter.exe
if exist "%~dp0dist\fastfilter.exe" (
    echo Standalone CLI Executable: %~dp0dist\fastfilter.exe
)
echo.
explorer "%~dp0dist"
pause