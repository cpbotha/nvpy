# -*- mode: python -*-

# to build this app, do from the top-level nvpy directory containing this spec:
# pyinstaller -w nvpy.spec

block_cipher = None


a = Analysis(['nvpy/nvpy.py'],
             pathex=['nvpy'],
             binaries=None,
             datas=[('nvpy/icons/nvpy.gif', 'icons')],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='nvpy',
          debug=False,
          strip=False,
          upx=True,
          console=False )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='nvpy')
app = BUNDLE(coll,
             name='nvpy.app',
             icon='nvpy/icons/nvpy.icns',
             bundle_identifier='com.vxlabs.nvpy',
             info_plist={
                 # for high-dpi / retina support
                 'NSHighResolutionCapable': 'True'
             })
