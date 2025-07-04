:: Step 1: Read version string from a text file
set /p VERSION=<overstim\version.txt

:: Display the version for verification
echo Version read from file: %VERSION%

:: Step 2: Call PyInstaller command
echo Running PyInstaller...
venv\Scripts\pyinstaller.exe --add-data=assets:assets --contents-directory="." --icon="assets\icon.ico" --noconfirm OverStim.pyw

:: Check if PyInstaller command was successful
if %ERRORLEVEL% neq 0 (
    echo PyInstaller command failed.
    exit /b %ERRORLEVEL%
)

:: Step 3: Call Inno Setup command
echo Running Inno Setup...
iscc setup.iss

:: Check if Inno Setup command was successful
if %ERRORLEVEL% neq 0 (
    echo Inno Setup command failed.
    exit /b %ERRORLEVEL%
)

echo Script completed successfully.
