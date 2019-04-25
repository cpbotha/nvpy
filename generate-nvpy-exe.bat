rem This batch generates an executable file for Windows.
rem
rem Requirements:
rem   Windows 10
rem   python 2.7
rem   PyInstaller

del dist\nvpy.exe
del dist\nvpy-debug.exe
python setup.py clean
pyinstaller --onefile -i nvpy\icons\nvpy.ico --add-binary "nvpy\icons\nvpy.gif;icons" -n nvpy       --windowed start-nvpy.py
pyinstaller --onefile -i nvpy\icons\nvpy.ico --add-binary "nvpy\icons\nvpy.gif;icons" -n nvpy-debug --console  start-nvpy.py
