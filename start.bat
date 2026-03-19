@echo off
echo ===================================================
echo     Starting Steganography Website...
echo ===================================================
echo.
echo Please leave this window open as long as you are using the website.
echo When you are completely done, simply close this window.
echo.
call venv\Scripts\activate.bat
python app.py
pause
