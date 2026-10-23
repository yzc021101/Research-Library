"""Bounded parser prefetch with owned scratch storage and cancellation."""
import json
import os
import subprocess
import tempfile
import time
import signal
from pathlib import Path
from paths import ROOT, worker_command
from spooled import Spool

def extract(library, path, doc_id):
    with tempfile.TemporaryDirectory(prefix='ingest-', dir=ROOT/'tmp') as name:
        folder = Path(name)
        (folder/'job.json').write_text(json.dumps({'path': str(path), 'doc_id': doc_id, 'settings': library.settings()}), encoding='utf-8')
        with (folder/'worker.log').open('wb') as log:
            child = subprocess.Popen(worker_command('ingest_worker', folder), stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                start_new_session=os.name != 'nt')
            started = time.monotonic()
            try:
                while child.poll() is None:
                    if library.sync_cancel.wait(.15): raise InterruptedError('同步已取消')
                    if time.monotonic()-started > 1800: raise TimeoutError('单文件解析超过 30 分钟，请单独重试或拆分文件。')
                    # Parallel workers never overwrite another file's foreground progress.
                    if library.progress().get('file') == path.name:
                        try: library.set_progress(**json.loads((folder/'progress.json').read_text(encoding='utf-8')))
                        except (OSError, ValueError): pass
                if child.returncode: raise RuntimeError(f'文件解析进程异常退出（{child.returncode}），请重试此文件。')
            finally:
                if child.poll() is None:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    else:
                        try: os.killpg(child.pid, signal.SIGTERM)
                        except ProcessLookupError: pass
                    try: child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        if os.name != 'nt':
                            try: os.killpg(child.pid, signal.SIGKILL)
                            except ProcessLookupError: pass
                        else: child.kill()
                        child.wait()
        result = json.loads((folder/'result.json').read_text(encoding='utf-8'))
        if 'error' in result: raise ValueError(result['error'])
        result['metadata']['_parse_seconds'] = time.monotonic()-started
        rows = []
        for part in ('pages', 'chunks'):
            with (folder/(part+'.jsonl')).open(encoding='utf-8') as source:
                rows.append(Spool(tuple(json.loads(line)) for line in source))
        return result['metadata'], *rows
