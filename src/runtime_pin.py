"""Run long-lived MCP bridges from immutable per-build paths across app updates."""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import atexit
import re
from pathlib import Path

def process_alive(pid):
    if os.name == 'nt':
        # os.kill(pid, 0) does not implement a harmless probe on Windows.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle: return ctypes.get_last_error() != 87
        try: return kernel.WaitForSingleObject(handle, 0) != 0
        finally: kernel.CloseHandle(handle)
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False
    except OSError: return True

def prepared_server():
    from paths import ROOT
    source = Path(sys.executable).resolve().parent
    base = ROOT/'data/mcp-runtimes'
    if source.parent == base: return source/Path(sys.executable).name
    digest = hashlib.sha256()
    for file in (Path(sys.executable), source/'_internal/base_library.zip'):
        with file.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''): digest.update(block)
    target = base/digest.hexdigest()[:24]
    base.mkdir(parents=True, exist_ok=True)
    # Keep every live bridge's runtime. Remove only our inactive, old generations.
    for old in base.iterdir():
        if old == target or not re.fullmatch(r'[0-9a-f]{24}', old.name) or old.is_symlink(): continue
        marker = old/'.complete'
        if not marker.is_file() or time.time()-marker.stat().st_mtime < 7*86400: continue
        alive = False
        for lease in (old/'.leases').glob('*'):
            try:
                if process_alive(int(lease.name)): alive = True
                else: lease.unlink(missing_ok=True)
            except (OSError, ValueError): alive = True
        if not alive: shutil.rmtree(old, ignore_errors=True)
    if not (target/'.complete').is_file():
        with tempfile.TemporaryDirectory(prefix='.preparing-', dir=base) as scratch:
            stage = Path(scratch)/'engine'
            def copy(src, dst):
                # macOS copy-on-write clones avoid doubling disk use. A failed clone
                # falls back to an independent copy; never use a mutable symlink.
                if sys.platform == 'darwin':
                    import ctypes
                    libc = ctypes.CDLL(None, use_errno=True)
                    if libc.clonefile(os.fsencode(src), os.fsencode(dst), 0) == 0: return dst
                return shutil.copy2(src, dst)
            shutil.copytree(source, stage, copy_function=copy, symlinks=False)
            (stage/'.complete').write_text(digest.hexdigest(), encoding='ascii')
            try: stage.rename(target)
            except OSError:
                if not (target/'.complete').is_file(): raise
    executable = target/Path(sys.executable).name
    return executable

def prepare_launcher_runtime():
    from paths import ROOT
    executable = prepared_server()
    temporary = ROOT/'data'/('mcp-runtime-'+str(os.getpid())+'.tmp')
    temporary.write_text(executable.parent.name, encoding='ascii')
    temporary.replace(ROOT/'data/mcp-runtime.txt')

def write_windows_launcher():
    from paths import ROOT
    # Keep the script ASCII. Unicode paths travel in environment variables, and
    # the helper returns only an ASCII content hash, independent of console locale.
    lines = ['@echo off', 'setlocal DisableDelayedExpansion',
             'if not defined RESEARCH_LIBRARY_ROOT exit /b 1',
             'if not defined RESEARCH_LIBRARY_ENGINE exit /b 1',
             '"%RESEARCH_LIBRARY_ENGINE%" prepare_mcp',
             'if errorlevel 1 exit /b 1',
             'set /p "RL_MCP_VERSION="<"%RESEARCH_LIBRARY_ROOT%\\data\\mcp-runtime.txt"',
             'if not defined RL_MCP_VERSION exit /b 1',
             '"%RESEARCH_LIBRARY_ROOT%\\data\\mcp-runtimes\\%RL_MCP_VERSION%\\research-library-engine.exe" server',
             'exit /b %errorlevel%']
    launcher=ROOT/'run-mcp.cmd'
    temporary=ROOT/('run-mcp-'+str(os.getpid())+'.tmp')
    temporary.write_bytes(('\r\n'.join(lines)+'\r\n').encode('utf-8'))
    temporary.replace(launcher)
    return launcher

def pin_server():
    if not getattr(sys, 'frozen', False) or len(sys.argv) < 2 or sys.argv[1] != 'server': return False
    executable=prepared_server()
    if Path(sys.executable).resolve() == executable:
        leases=executable.parent/'.leases';leases.mkdir(exist_ok=True)
        lease=leases/str(os.getpid());lease.touch()
        atexit.register(lambda:lease.unlink(missing_ok=True))
        return False
    # Compatibility for direct engine commands. Windows generated client config
    # uses run-mcp.cmd so this installed executable exits before the session starts.
    # No output is written to stdout before the MCP handshake.
    env = dict(os.environ)
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    if os.name != 'nt':
        os.execve(str(executable), [str(executable), *sys.argv[1:]], env)
    code = subprocess.call([str(executable), *sys.argv[1:]], env=env,
                           stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    raise SystemExit(code)
