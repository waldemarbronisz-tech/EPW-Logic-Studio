@echo off
echo Starting EPW Logic Studio...
:: Start script for Windows environments
python.exe -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
python main.py
