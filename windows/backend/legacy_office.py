"""Read-only legacy Office conversion, isolated from the user's LibreOffice profile.

The original file remains the library identity. Only a private copy is passed to
LibreOffice; committed OOXML output is content-addressed and checked on reuse.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

from paths import ROOT

FORMATS = {'.doc': ('docx', 'Office Open XML Text'),
           '.ppt': ('pptx', 'Impress MS PowerPoint 2007 XML'),
           '.xls': ('xlsx', 'Calc MS Excel 2007 XML')}
CONVERSION_VERSION = 1
TIMEOUT = 120
MAX_BYTES = 100 * 1024 * 1024


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def cancelled(event):
    if event is not None and event.is_set():
        raise InterruptedError('同步已取消；已完成的文档保留，下次同步可继续。')


def converter():
    override = os.environ.get('RESEARCH_LIBRARY_SOFFICE')
    if override:
        candidates = [Path(override)]
    elif os.name == 'nt':
        candidates = [ROOT/'components/legacy-office/program/soffice.com', ROOT.parent/'tools/libreoffice/program/soffice.com',
                      ROOT/'tools/libreoffice/program/soffice.com']
        candidates += [Path(os.environ.get(k, 'C:/Program Files'))/'LibreOffice/program/soffice.com'
                       for k in ('ProgramFiles', 'ProgramFiles(x86)')]
    else:
        candidates = [ROOT/'components/legacy-office/LibreOffice.app/Contents/MacOS/soffice', ROOT/'tools/LibreOffice.app/Contents/MacOS/soffice',
                      Path('/Applications/LibreOffice.app/Contents/MacOS/soffice')]
    for p in candidates:
        if p.is_file(): return p.resolve()
    raise RuntimeError('旧版 Office 转换组件不可用：需要 LibreOffice。请在设置的可选组件中安装转换组件，或安装 LibreOffice，然后重新同步；原文件未修改。')


def write_profile(profile):
    """Explicitly disable macros, OLE/DDE and document-originated external links."""
    user = profile/'user'
    user.mkdir(parents=True)
    user.joinpath('registrymodifications.xcu').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">
 <prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
 <prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
 <prop oor:name="DisableActiveContent" oor:op="fuse"><value>true</value></prop>
 <prop oor:name="DisableOLEAutomation" oor:op="fuse"><value>true</value></prop>
 <prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop>
</item>
<item oor:path="/org.openoffice.Office.Calc/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>1</value></prop></item>
<item oor:path="/org.openoffice.Office.Writer/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>2</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop></item>
</oor:items>''', encoding='utf-8')


def stop_process(process):
    # Each invocation has its own profile and process tree. Never kill by app name.
    if os.name == 'nt':
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
    else:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    if process.poll() is None: process.kill()
    process.wait(timeout=10)


def run_conversion(source, output, profile, target, event=None, timeout=TIMEOUT, executable=None):
    """Also used by fixture generation with the exact same isolated profile."""
    cancelled(event)
    executable = Path(executable) if executable else converter()
    write_profile(profile)
    output.mkdir(parents=True, exist_ok=True)
    command = [str(executable), '-env:UserInstallation='+profile.resolve().as_uri(),
               '--headless', '--nologo', '--nodefault', '--nofirststartwizard', '--norestore',
               '--convert-to', target, '--outdir', str(output.resolve()), str(source.resolve())]
    env = {**os.environ, 'TMPDIR': str(profile.parent), 'TMP': str(profile.parent),
           'TEMP': str(profile.parent), 'SAL_DISABLE_OPENCL': '1'}
    # A regular log avoids pipe deadlocks and allows bounded diagnostic reads.
    with (profile.parent/'conversion.log').open('wb+') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, env=env,
            stdin=subprocess.DEVNULL, start_new_session=os.name != 'nt',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        start = time.monotonic()
        try:
            while process.poll() is None:
                cancelled(event)
                if time.monotonic()-start > timeout:
                    raise TimeoutError(f'旧版 Office 转换超过 {timeout:g} 秒，已停止；可检查文件后重试。')
                time.sleep(.1)
            cancelled(event)
        except BaseException:
            stop_process(process)
            raise
        log.flush(); log.seek(0)
        message = log.read(4096).decode('utf-8', errors='replace')
    if process.returncode:
        raise ValueError(f'旧版 Office 转换失败（退出码 {process.returncode}）；原文件未修改。{message[-800:]}')
    return message


@contextmanager
def conversion_workspace(parent):
    """Clean LibreOffice profiles even when child paths exceed Windows MAX_PATH."""
    folder = Path(tempfile.mkdtemp(prefix='legacy-office-', dir=parent))
    try:
        yield folder
    finally:
        target = str(folder.resolve())
        if os.name == 'nt':
            target = ('\\\\?\\UNC\\' + target[2:]) if target.startswith('\\\\') else ('\\\\?\\' + target)
        shutil.rmtree(target)


def convert(path, progress=None, cancel=None, timeout=TIMEOUT):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in FORMATS: raise ValueError('不是支持的旧版 Office 格式。')
    if path.stat().st_size > MAX_BYTES: raise ValueError('旧版 Office 文件超过 100 MB 转换限制。')
    cancelled(cancel)
    with path.open('rb') as stream: header = stream.read(8)
    if header != bytes.fromhex('d0cf11e0a1b11ae1') and not (suffix == '.doc' and header.startswith(b'{\\rtf')):
        raise ValueError('文件内容与旧版 Office 格式不符：支持 Office 97–2003 DOC/PPT/XLS；请检查文件是否损坏或扩展名错误。')
    executable = converter()
    sha = digest(path)
    stat = executable.stat()
    engine_id = f'{executable}:{stat.st_size}:{stat.st_mtime_ns}'
    target, filter_name = FORMATS[suffix]
    key = hashlib.sha256(f'{sha}:{suffix}:{CONVERSION_VERSION}:{engine_id}'.encode()).hexdigest()
    cache = ROOT/'cache/legacy-office'/key
    output, manifest = cache/('document.'+target), cache/'conversion.json'
    if progress: progress(stage='converting', file=path.name, location=f'{suffix[1:].upper()} → {target.upper()}', image=None)
    try:
        meta = json.loads(manifest.read_text(encoding='utf-8'))
        if meta['source_sha256'] == sha and output.is_file() and digest(output) == meta['converted_sha256']:
            cancelled(cancel)
            return output, {**meta, 'cache_hit': True}
    except (OSError, ValueError, KeyError): pass
    tmp = ROOT/'tmp'; tmp.mkdir(parents=True, exist_ok=True)
    with conversion_workspace(tmp) as folder:
        work = Path(folder)
        source = work/('document'+suffix)
        shutil.copyfile(path, source)
        if digest(source) != sha or digest(path) != sha:
            raise RuntimeError('原文件在复制时发生变化，请保存完成后重新同步。')
        run_conversion(source, work/'output', work/'profile', target+':'+filter_name, cancel, timeout, executable)
        derived = work/'output'/('document.'+target)
        if not derived.is_file() or derived.stat().st_size == 0:
            raise ValueError('旧版 Office 未生成可读取副本：文件可能已加密、损坏或内容与扩展名不符。请检查原文件；原文件未修改。')
        if derived.stat().st_size > MAX_BYTES:
            raise ValueError('转换副本超过 100 MB 读取限制。')
        from document_formats import check_package
        check_package(derived)
        cancelled(cancel)
        if digest(path) != sha: raise RuntimeError('原文件在转换时发生变化，请保存完成后重新同步。')
        meta = {'engine': 'LibreOffice', 'conversion_version': CONVERSION_VERSION,
                'source_format': suffix[1:], 'target_format': target,
                'source_sha256': sha, 'converted_sha256': digest(derived),
                'derived_path': str(output.relative_to(ROOT)),
                'location_basis': 'converted_copy', 'cache_hit': False}
        cache.mkdir(parents=True, exist_ok=True)
        os.replace(derived, output)
        pending = work/'manifest.json'
        pending.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(pending, manifest)
    return output, meta
