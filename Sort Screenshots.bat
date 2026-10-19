@echo off
rem Double-click this file after Organize Photos.bat has finished. It pulls
rem one app's screenshots out of _review\screenshots into their own folder,
rem using example screenshots you put in the examples folder next to it.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Sort Screenshots

echo.
echo  ===== Sort Screenshots =====
echo  Moves one app's screenshots out of _review\screenshots into a folder
echo  of their own. Nothing is deleted.
echo.

call :find_python
if not defined PY (
    echo  Python was not found. Double-click Organize Photos.bat first; it
    echo  sets everything up.
    goto :end
)
%PY% -m pip install --disable-pip-version-check --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo  Setup failed. Check the internet connection and try again.
    goto :end
)

set "EXAMPLES=%~dp0examples"
if not exist "!EXAMPLES!\" mkdir "!EXAMPLES!"
dir /b /a-d "!EXAMPLES!" 2>nul | findstr . >nul
if errorlevel 1 (
    echo  First, show it what the app's screenshots look like. A folder
    echo  called "examples" is opening now. Copy one of the app's
    echo  screenshots into it ^(from _review\screenshots on the new drive^).
    echo  If the app's look changed over the years, copy one of each look.
    start "" "!EXAMPLES!"
    echo.
    echo  When the example is in the folder, come back here.
    pause
    dir /b /a-d "!EXAMPLES!" 2>nul | findstr . >nul
    if errorlevel 1 (
        echo  The examples folder is still empty. Nothing was moved.
        goto :end
    )
)

echo  Where is the Organized folder? Type the letter of the drive it is on
echo  (like D), or drag the Organized folder onto this window. Then press
echo  Enter.
echo.
:ask_output
set "ANSWER="
set /p "ANSWER= Organized is on: "
if not defined ANSWER goto :ask_output
call :to_path ANSWER
if not defined RESULT (
    echo    That is not a drive or folder on this computer. Try again.
    goto :ask_output
)
rem The Organized folder itself, or the drive or folder it is in.
if "!RKIND!"=="drive" (set "OUT=!RDRIVE!:\Organized") else (set "OUT=!RESULT!")
if not exist "!OUT!\_review\screenshots\" if exist "!OUT!\Organized\_review\screenshots\" set "OUT=!OUT!\Organized"
if not exist "!OUT!\_review\screenshots\" (
    echo    No Organized folder with screenshots in it there. Check the
    echo    answer, or run Organize Photos.bat first.
    goto :ask_output
)
echo    Using !OUT!
echo.

:ask_name
set "NAME="
set /p "NAME= A one-word name for the app's folder (for example: music): "
if not defined NAME goto :ask_name
set "NAME=!NAME: =_!"

echo.
echo  Step 1 of 2: a preview. Nothing is moved.
echo.
%PY% sort_screenshots.py --output "!OUT!" --examples "!EXAMPLES!" --name "!NAME!" --dry-run
if errorlevel 1 goto :end

echo.
echo  The "matched" number above is how many screenshots would move.
echo.
set "GO="
set /p "GO= Type Y and press Enter to move them (anything else stops): "
if /i not "!GO!"=="Y" (
    echo  Stopped. Nothing was moved.
    goto :end
)

echo.
echo  Step 2 of 2: moving.
echo.
%PY% sort_screenshots.py --output "!OUT!" --examples "!EXAMPLES!" --name "!NAME!"
if exist "!OUT!\_review\!NAME!" start "" "!OUT!\_review\!NAME!"
echo.
echo  If some of the app's screenshots were missed, copy one of them into
echo  the examples folder and double-click this file again. Only what is
echo  still in _review\screenshots is checked.

:end
echo.
pause
exit /b

:to_path
rem Turns an answer into a path. A letter, with or without : and \, is the
rem whole drive (RESULT=E:\, RKIND=drive). Anything else is a folder, as
rem typed or dragged in with quotes (RESULT without a trailing \,
rem RKIND=folder). RDRIVE is the drive letter. RESULT is empty when the
rem drive or folder does not exist.
set "RESULT="
set "RDRIVE="
set "RKIND="
set "P=!%1!"
set "P=!P:"=!"
:to_path_front
if not defined P exit /b
if "!P:~0,1!"==" " set "P=!P:~1!" & goto :to_path_front
:to_path_back
if not defined P exit /b
if "!P:~-1!"==" " set "P=!P:~0,-1!" & goto :to_path_back
set "D=!P::=!"
set "D=!D:\=!"
if "!P:~3!"=="" if defined D if "!D:~1!"=="" (
    call :upper D
    if not exist "!D!:\" exit /b
    set "RESULT=!D!:\"
    set "RDRIVE=!D!"
    set "RKIND=drive"
    exit /b
)
if "!P:~-1!"=="\" set "P=!P:~0,-1!"
if not exist "!P!\" exit /b
set "D=!P:~0,1!"
call :upper D
set "RESULT=!D!!P:~1!"
set "RDRIVE=!D!"
set "RKIND=folder"
exit /b

:upper
for %%u in (A B C D E F G H I J K L M N O P Q R S T U V W X Y Z) do set "%1=!%1:%%u=%%u!"
exit /b

:find_python
rem Ignores the Microsoft Store placeholder, which is on PATH but cannot
rem run anything.
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3" && exit /b
python --version >nul 2>&1 && set "PY=python" && exit /b
for %%p in ("%LOCALAPPDATA%\Programs\Python\Launcher\py.exe") do (
    if exist "%%~p" "%%~p" -3 --version >nul 2>&1 && set PY="%%~p" -3 && exit /b
)
for /d %%p in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%~p\python.exe" set PY="%%~p\python.exe"
)
exit /b
