rem This batch generates an executable file for Windows.
rem
rem Requirements:
rem   Windows 10
rem   Python 3.7 and Python launcher
rem   PyInstaller
rem
rem Output:
rem   dist\nvpy-windows.zip
rem   dist\nvpy-windows-debug.zip

rem Remove build cache and executable files before starting build.
rmdir /q /s build
del dist\nvpy.exe
del dist\nvpy-debug.exe

rem Upgrade pyinstaller.
py -3 -m pip install --upgrade pyinstaller

rem When you generate windows binary, you need the certifi package.
rem See workaround code on nvpy.py for details.
py -3 -m pip install --upgrade certifi

rem Install dependencies.
rem When build nvpy on the clean environment, this process is required.
py -3 -m pip install --upgrade Markdown docutils simplenote

py -3 setup.py clean

rem Generate one-folder bundles.
rem NOTE:
rem   The one-file bundles have a start-up performance issue.  Therefore, the one-file bundle is no longer provided.
py -3 -m PyInstaller -i nvpy\icons\nvpy.ico --add-binary "nvpy\icons\nvpy.gif;icons" -n nvpy       --windowed start-nvpy.py
py -3 -m PyInstaller -i nvpy\icons\nvpy.ico --add-binary "nvpy\icons\nvpy.gif;icons" -n nvpy-debug --console  start-nvpy.py
echo Compress-Archive dist/nvpy dist/nvpy-windows.zip             |powershell -Command -
echo Compress-Archive dist/nvpy-debug dist/nvpy-windows-debug.zip |powershell -Command -
