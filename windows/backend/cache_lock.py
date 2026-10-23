"""Per-content cross-process cache locks; OS releases locks after cancellation."""
from contextlib import contextmanager
import time
from filelock import FileLock, Timeout
from paths import ROOT

@contextmanager
def locked(key, event=None, timeout=1800):
    folder=ROOT/'cache/locks';folder.mkdir(parents=True,exist_ok=True)
    lock=FileLock(str(folder/(key+'.lock')))
    start=time.monotonic()
    while True:
        if event is not None and event.is_set():raise InterruptedError('同步已取消')
        if time.monotonic()-start>timeout:raise TimeoutError('等待同一文件的缓存处理超时，请重试。')
        try:lock.acquire(timeout=.2);break
        except Timeout:pass
    try:yield
    finally:lock.release()
