# -*- mode: python -*-
a = Analysis(["masterskaya.py"], pathex=[], datas=[],
             hiddenimports=["openpyxl", "openpyxl.styles", "csv", "copy", "itertools", "secrets", "collections",
                            "http.server", "urllib.parse", "json", "math", "subprocess", "threading", "socket"],
             excludes=["tkinter"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [("X utf8", None, "OPTION")], exclude_binaries=True, name="Мастерская",
          icon="icon.png", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="Мастерская")
