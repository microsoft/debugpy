@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1

:: No argument preserves the x86/x64 build. ARM64 is explicitly requested.
set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=all"
if not "%~2"=="" goto usage
if /i "%TARGET%"=="all" goto find_x86_tools
if /i "%TARGET%"=="x86" goto find_x86_tools
if /i "%TARGET%"=="amd64" goto find_x86_tools
if /i "%TARGET%"=="arm64" goto find_arm64_tools
goto usage

:find_x86_tools
set "COMPONENTS=Microsoft.VisualStudio.Component.VC.Tools.x86.x64"
goto find_tools

:find_arm64_tools
set "COMPONENTS=Microsoft.VisualStudio.Component.VC.Tools.ARM64 Microsoft.VisualStudio.Component.VC.Runtimes.ARM64.Spectre"

:find_tools
set "PYDEVD_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%PYDEVD_VSWHERE%" (
    echo ERROR: vswhere not found at "%PYDEVD_VSWHERE%". 1>&2
    exit /b 1
)
set "VSDIR="
for /f "usebackq tokens=*" %%i in (`"%PYDEVD_VSWHERE%" -prerelease -latest -products * -requires %COMPONENTS% -property installationPath`) do set "VSDIR=%%i"
if not defined VSDIR (
    echo ERROR: Visual Studio components required for %TARGET% are missing: %COMPONENTS%. 1>&2
    exit /b 1
)
echo Using Visual C++ at "%VSDIR%"
if not exist "%VSDIR%\VC\Auxiliary\Build\vcvarsall.bat" (
    echo ERROR: vcvarsall.bat not found. 1>&2
    exit /b 1
)

if /i "%TARGET%"=="arm64" (
    call :build_arch x64_arm64 arm64 ""
    if errorlevel 1 exit /b 1
    exit /b 0
)
if /i "%TARGET%"=="all" goto build_x86
if /i "%TARGET%"=="x86" goto build_x86
goto build_amd64

:build_x86
call :build_arch x86 x86 /CETCOMPAT
if errorlevel 1 exit /b 1
if /i "%TARGET%"=="x86" exit /b 0

:build_amd64
call :build_arch x86_amd64 amd64 /CETCOMPAT
if errorlevel 1 exit /b 1
exit /b 0

:build_arch
setlocal
call "%VSDIR%\VC\Auxiliary\Build\vcvarsall.bat" %~1 -vcvars_spectre_libs=spectre
if errorlevel 1 exit /b 1
where cl.exe >nul 2>&1
if errorlevel 1 (
    echo ERROR: MSVC compiler not found for %~2. 1>&2
    exit /b 1
)
set "LIBARCH=%~2"
if "%LIBARCH%"=="amd64" set "LIBARCH=x64"
if not exist "%VCToolsInstallDir%lib\spectre\%LIBARCH%\libcmt.lib" (
    echo ERROR: Spectre libraries not found for %~2. 1>&2
    exit /b 1
)

cl -DUNICODE -D_UNICODE /EHsc /Zi /Fdhelper_%~2.pdb /O1 /W3 /LD /MD /GL /Qspectre /guard:cf attach.cpp /link /LTCG /PROFILE /GUARD:CF %~3 /out:attach_%~2.dll /implib:attach_%~2.lib
if errorlevel 1 exit /b 1
cl -DUNICODE -D_UNICODE /EHsc /Zi /Fdhelper_%~2.pdb /O1 /W3 /LD /MD /GL /Qspectre /guard:cf run_code_on_dllmain.cpp /link /LTCG /PROFILE /GUARD:CF %~3 /out:run_code_on_dllmain_%~2.dll /implib:run_code_on_dllmain_%~2.lib
if errorlevel 1 exit /b 1
cl /EHsc /Zi /Fdhelper_%~2.pdb /O1 /W3 /GL /Qspectre /guard:cf inject_dll.cpp /link /LTCG /PROFILE /GUARD:CF %~3 /out:inject_dll_%~2.exe
if errorlevel 1 exit /b 1

for %%f in (attach_%~2.dll attach_%~2.pdb run_code_on_dllmain_%~2.dll run_code_on_dllmain_%~2.pdb inject_dll_%~2.exe inject_dll_%~2.pdb) do (
    copy /Y "%%f" "..\%%f" >nul
    if errorlevel 1 exit /b 1
)
del /Q attach_%~2.dll attach_%~2.pdb run_code_on_dllmain_%~2.dll run_code_on_dllmain_%~2.pdb inject_dll_%~2.exe inject_dll_%~2.pdb
del /Q attach.obj run_code_on_dllmain.obj inject_dll.obj attach_%~2.lib attach_%~2.exp run_code_on_dllmain_%~2.lib run_code_on_dllmain_%~2.exp helper_%~2.pdb
exit /b 0

:usage
echo Usage: compile_windows.bat [all^|x86^|amd64^|arm64] 1>&2
exit /b 2
