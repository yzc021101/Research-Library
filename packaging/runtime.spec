# Built separately on each OS; bundles the interpreter and runtime dependencies only.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules
source = Path(os.environ['RL_SOURCE'])
hidden = ['backend','server','model_worker','settings_cli','check_mcp','package_smoke','components']
hidden += collect_submodules('fastembed')
datas = []
for name in ('fastembed','mcp','lancedb','onnxruntime','tokenizers','huggingface_hub'):
    datas += copy_metadata(name)
for name in ('fastembed','docx','pptx','striprtf'):
    datas += collect_data_files(name)
a = Analysis([str(source/'runtime_entry.py')], pathex=[str(source)], datas=datas,
    hiddenimports=hidden, excludes=['matplotlib','IPython','jupyter','pytest','tkinter','torch','tensorflow','sympy'], noarchive=False)
pyz = PYZ(a.pure)
# Microsoft CRT is installed from Microsoft on the end user's machine.
# Wheels sometimes import hashed CRT filenames; record aliases, not CRT binaries.
if os.name == 'nt':
    import json, re, tempfile
    aliases = {}
    filtered = []
    for name, filename, kind in a.binaries:
        leaf = Path(name).name
        if re.match(r'^(msvcp140|vcruntime140|concrt140).*\.dll$', leaf, re.I):
            canonical = re.sub(r'-[a-fA-F0-9]{32}(?=\.dll$)', '', leaf)
            if canonical != leaf: aliases[leaf] = canonical
        else: filtered.append((name, filename, kind))
    a.binaries = filtered
    alias_file = Path(workpath)/'vc-aliases.json'
    alias_file.write_text(json.dumps(aliases, sort_keys=True))
    a.datas += [('vc-aliases.json',str(alias_file),'DATA')]
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='research-library-engine', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='research-library-engine')
