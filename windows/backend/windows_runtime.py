"""Use the user's installed Microsoft runtime, never redistribute copied CRT DLLs."""
import ctypes, json, os, shutil, sys
from pathlib import Path
_DLL_HANDLES=[]
def prepare_runtime_aliases():
    if os.name != 'nt' or not getattr(sys, 'frozen', False): return
    manifest=Path(sys._MEIPASS)/'vc-aliases.json'
    if not manifest.exists(): return
    from paths import ROOT
    target=ROOT/'runtime'/'vc-aliases';target.mkdir(parents=True,exist_ok=True)
    buf=ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(buf,len(buf)):raise OSError('Cannot locate Windows runtime')
    system=Path(buf.value)
    for alias,canonical in json.loads(manifest.read_text()).items():
        if Path(alias).name!=alias or Path(canonical).name!=canonical:raise ValueError('Invalid runtime alias')
        original=system/canonical;copy=target/alias
        if not original.is_file():raise RuntimeError('Microsoft Visual C++ runtime is missing. Open the app to download and install it.')
        if not copy.exists() or copy.stat().st_size!=original.stat().st_size or copy.stat().st_mtime_ns!=original.stat().st_mtime_ns:
            temporary=target/(alias+'.tmp-'+str(os.getpid()));shutil.copy2(original,temporary);os.replace(temporary,copy)
    _DLL_HANDLES.append(os.add_dll_directory(str(target)))
