rem This batch generates an executable file for Windows.
rem
rem Requirements:
rem   Windows 10
rem   python 2.7
rem   PyInstaller
rem
rem Output:
rem   dist\nvpy.exe
rem   dist\nvpy-debug.exe

rem Remove build cache and executable files before starting build.
rmdir /q /s build
del dist\nvpy.exe
del dist\nvpy-debug.exe

rem When you generate windows binary, you need the certifi package.
rem See workaround code on nvpy.py for details.
pip install --upgrade certifi

python setup.py clean
pyinstaller --onefile -i nvpy\icons\nvpy.ico --add-binary "nvpy\icons\nvpy.gif;icons" -n nvpy       --windowed start-nvpy.py
pyinstaller --onefile -i nvpy\icons\nvpy.ico --add-binary "nvpy\icons\nvpy.gif;icons" -n nvpy-debug --console  start-nvpy.py
