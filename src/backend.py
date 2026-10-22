"""Single local engine shared by the native app and MCP stdio bridges."""
from paths import ROOT, worker_command
from settings import load_settings, save_settings
from library import Library
from models import catalog, spec, asset_marker, available, remove_asset
import subprocess
import sys
import uuid
import fcntl
import json
import os
import secrets
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RUNTIME = ROOT / "data/service.json"

class Engine:
    def __init__(self):
        from components import ComponentManager
        self.components = ComponentManager()
        self.library = Library(load_settings)
        self.state_lock = threading.RLock()
        self.working = False
        self.last_error = None
        self.last_sync = None
        self.cached_status = self.library.status()
        self.stopping = threading.Event()
        self.configured_sources = load_settings()["source_folders"]
        self.pending_sync = False
        previous_cleanup = self.library.db.execute("SELECT value FROM library_config WHERE key='last_cleanup'").fetchone()
        self.last_cleanup = float(previous_cleanup[0]) if previous_cleanup else 0
        self.watch_signature = None
        self.model_process = None
        self.model_job = {"phase": "idle"}
        self.model_busy = False
        self.model_cancel = threading.Event()
        self.job_file = ROOT / "data/model-job.json"
        if self.job_file.exists():
            try:
                self.model_job = json.loads(self.job_file.read_text())
                if self.model_job.get("phase") in {"starting", "downloading", "indexing", "ready"}:
                    table = "model_" + self.model_job["job_id"]
                    if self.library.embedding["table"] == table:
                        self.model_job.update(phase="complete")
                    else:
                        self.model_job.update(phase="cancelled", error="上次模型任务被中断，继续使用原模型。")
                        try: self.library.vectors().drop_table(table)
                        except Exception: pass
                    self.persist_job()
            except (OSError, ValueError, KeyError): self.model_job = {"phase": "idle"}

    def persist_job(self):
        temp = self.job_file.with_suffix(".tmp")
        temp.write_text(json.dumps(self.model_job, ensure_ascii=False))
        temp.replace(self.job_file)

    def status(self):
        with self.state_lock:
            return {**self.cached_status, "running": True, "busy": self.working,
                "last_error": self.last_error, "last_sync": self.last_sync, "sync_progress": self.library.progress(),
                "model_loaded": self.library._embedder is not None, "pid": os.getpid(),
                "components": self.components.status(), "models": catalog(self.library.embedding["model"]), "model_job": dict(self.model_job)}

    def sync(self, retry=False, path=None):
        with self.state_lock:
            if self.working or self.model_busy or self.components.job['phase'] in ('installing', 'downloading'):
                if not retry: self.pending_sync = True
                return {"accepted": False, "reason": "busy" if retry else "queued_after_current_sync"}
            self.library.sync_cancel.clear()
            self.last_error = None
            self.working = True
        def work():
            try:
                result = self.library.sync(prepared=True, retry=retry, path=path)
                with self.state_lock:
                    self.cached_status = result["status"]
                    self.last_error = "同步已取消，已完成的文档保留。" if result.get("cancelled") else None
                    self.last_sync = time.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as exc:
                with self.state_lock: self.last_error = str(exc)
            finally:
                with self.state_lock:
                    self.working = False
                    pending = self.pending_sync
                    self.pending_sync = False
                if pending and not self.stopping.is_set(): self.sync()
        threading.Thread(target=work, daemon=True).start()
        return {"accepted": True}

    def cancel_sync(self):
        with self.state_lock:
            self.pending_sync = False
            if not self.working: return {'cancelling': False}
            result = self.library.cancel_sync()
            self.watch_signature = self.library.file_signature()
            return result

    def switch_model(self, model_id):
        spec(model_id)
        with self.state_lock:
            if self.working or self.model_busy or self.components.job['phase'] in ('installing', 'downloading'): raise ValueError("请等待当前同步或模型任务完成。")
            self.model_busy = True
            self.model_cancel.clear()
            job_id = uuid.uuid4().hex
            self.model_job = {"phase": "starting", "model": model_id, "job_id": job_id, "completed": 0, "total": 0}
            self.persist_job()
        folder = ROOT / "data/model-jobs" / job_id
        folder.mkdir(parents=True)
        table_name = "model_" + job_id
        def work():
            committed = False
            old_table = self.library.embedding["table"]
            try:
                local_only = available(model_id)
                with open(folder / "worker.log", "w") as log:
                    process = subprocess.Popen(worker_command("model_worker", model_id, table_name, folder, "local-only" if local_only else "download"), stdout=log, stderr=log)
                    with self.state_lock: self.model_process = process
                    while process.poll() is None:
                        if self.model_cancel.is_set() or self.stopping.is_set():
                            process.terminate()
                            try: process.wait(timeout=3)
                            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
                            break
                        try:
                            progress = json.loads((folder / "progress.json").read_text())
                            with self.state_lock:
                                if any(self.model_job.get(k) != v for k, v in progress.items()):
                                    self.model_job.update(progress)
                                    self.persist_job()
                        except (OSError, ValueError): pass
                        time.sleep(.2)
                    if self.model_cancel.is_set() or self.stopping.is_set(): raise InterruptedError("模型任务已取消，继续使用原模型。")
                    if process.returncode != 0:
                        raise RuntimeError("下载或索引构建失败，继续使用原模型。详情见资料库 data/model-jobs/" + job_id + "/worker.log")
                result = json.loads((folder / "result.json").read_text())
                if result["model"] != model_id or result["table"] != table_name: raise ValueError("模型任务结果不匹配")
                # Cancel and commit are serialized, so a reported cancellation cannot commit later.
                with self.state_lock:
                    if self.model_cancel.is_set() or self.stopping.is_set(): raise InterruptedError("模型任务已取消，继续使用原模型。")
                    self.library.activate_model(result)
                    committed = True
                    self.cached_status = self.library.status()
                    self.model_job.update(phase="complete", completed=result["count"], total=result["count"])
                    self.last_error = None
                try: self.library.vectors().drop_table(old_table)
                except Exception: pass  # Active pointer is already durable; stale table can be cleaned later.
            except InterruptedError as exc:
                with self.state_lock: self.model_job.update(phase="cancelled", error=str(exc))
            except Exception as exc:
                with self.state_lock: self.model_job.update(phase="failed", error=str(exc))
            finally:
                if not committed:
                    try: self.library.vectors().drop_table(table_name)
                    except Exception: pass
                with self.state_lock:
                    self.model_busy = False
                    self.model_process = None
                    self.persist_job()
                    pending = self.pending_sync
                    self.pending_sync = False
                if pending and not self.stopping.is_set(): self.sync()
        threading.Thread(target=work, daemon=True).start()
        return {"accepted": True, "job_id": job_id}

    def component_action(self, action, data):
        with self.state_lock:
            if self.working or self.model_busy or self.components.job['phase'] in ('installing', 'downloading'): raise ValueError("请先等待同步或模型任务结束。")
            if action == 'remove': return self.components.remove(data['id'])
            return self.components.start(data['id'], data.get('path'))

    def remove_model(self, model):
        spec(model)
        with self.state_lock:
            if self.working or self.model_busy or self.components.job['phase'] in ('installing', 'downloading'): raise ValueError("请先等待同步或模型任务结束。")
            with self.library.lock:
                if model == self.library.embedding['model']:
                    self.library._embedder = None
                remove_asset(model)
            return {'removed': True}

    def cancel_model(self):
        with self.state_lock:
            if not self.model_busy: return {"accepted": False}
            self.model_cancel.set()
        return {"accepted": True}

    def storage_action(self, mode=None):
        with self.state_lock:
            if self.working or self.model_busy or self.components.job['phase'] in ('installing', 'downloading'):
                raise ValueError('请等待同步、模型或组件任务完成。')
            self.working = True
        try:
            if mode == 'snapshots' and load_settings().get('keep_snapshots', False):
                raise ValueError('请先关闭保留原文快照，再移除全部副本。')
            result = self.library.cleanup_storage(mode) if mode else self.library.storage_status()
            if mode:
                if mode == 'expired':
                    self.last_cleanup = time.time()
                    with self.library.lock:
                        self.library.db.execute("INSERT OR REPLACE INTO library_config VALUES('last_cleanup',?)", (str(self.last_cleanup),))
                        self.library.db.commit()
                with self.state_lock: self.cached_status = self.library.status()
            return result
        finally:
            with self.state_lock:
                self.working = False
                pending = self.pending_sync
                self.pending_sync = False
            if pending and not self.stopping.is_set(): self.sync()

    def watch(self):
        while not self.stopping.is_set():
            cfg = load_settings()
            try:
                if time.time()-self.last_cleanup > 86400 and not self.working and not self.model_busy:
                    self.storage_action('expired')
                    self.last_cleanup = time.time()
                if not self.working and not self.model_busy: self.library.release_idle_model()
                current = self.library.file_signature() if cfg["auto_scan"] else self.watch_signature
                if cfg["auto_scan"] and current != self.watch_signature and not self.working and not self.model_busy:
                    if self.sync()["accepted"]: self.watch_signature = current
            except Exception as exc:
                with self.state_lock: self.last_error = str(exc)
            self.stopping.wait(cfg["scan_interval"])

    def tool(self, name, args):
        if name == "library_status": return self.status()
        if name == "sync_library":
            # MCP keeps the synchronous contract; UI uses background /sync instead.
            with self.state_lock:
                if self.working or self.model_busy or self.components.job['phase'] in ('installing', 'downloading'): raise ValueError("正在同步或切换模型，请稍后重试。")
                self.library.sync_cancel.clear()
                self.working = True
            try:
                result = self.library.sync(prepared=True)
                with self.state_lock: self.cached_status = result["status"]
                return result
            finally:
                with self.state_lock:
                    self.working = False
                    pending = self.pending_sync
                    self.pending_sync = False
                if pending and not self.stopping.is_set(): self.sync()
        names = {"search_documents": self.library.search_documents,
                 "search_passages": self.library.search,
                 "read_document": self.library.read_document,
                 "read_unit": self.library.read_unit,
                 "read_page": self.library.read_page}
        if name not in names: raise ValueError("Unknown tool")
        return names[name](**args)

def main():
    own_group = False
    try:
        os.setsid()
        own_group = True
    except OSError:
        pass
    guard = open(ROOT / "data/backend.lock", "w")
    try: fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit("A local research engine is already running")
    engine = Engine()
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def send(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        def authorized(self):
            return secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)
        def do_GET(self):
            if not self.authorized(): return self.send(401, {"error": "unauthorized"})
            if self.path == "/status": return self.send(200, engine.status())
            if self.path == "/settings": return self.send(200, load_settings())
            return self.send(404, {"error": "not_found"})
        def do_POST(self):
            if not self.authorized(): return self.send(401, {"error": "unauthorized"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 100_000: return self.send(413, {"error": "request_too_large"})
                data = json.loads(self.rfile.read(size) or b"{}")
                if self.path == "/settings":
                    old_sources = engine.configured_sources
                    cfg = save_settings(data)
                    # Source removal takes effect immediately for both app and MCP results.
                    if cfg["source_folders"] != old_sources:
                        engine.configured_sources = cfg["source_folders"]
                        engine.sync()
                    return self.send(200, cfg)
                if self.path == "/storage/status": return self.send(200, engine.storage_action())
                if self.path == "/storage/cleanup": return self.send(200, engine.storage_action(data.get('mode', 'expired')))
                if self.path == "/models/switch": return self.send(200, engine.switch_model(data["model"]))
                if self.path == "/models/remove": return self.send(200, engine.remove_model(data['model']))
                if self.path == "/components/install": return self.send(200, engine.component_action('install', data))
                if self.path == "/components/remove": return self.send(200, engine.component_action('remove', data))
                if self.path == "/components/cancel":
                    engine.components.stop.set()
                    return self.send(200, {'cancelled':True})
                if self.path == "/models/cancel": return self.send(200, engine.cancel_model())
                if self.path == "/sync/cancel": return self.send(200, engine.cancel_sync())
                if self.path == "/imports/retry": return self.send(200, engine.sync(retry=True, path=data.get("path")))
                if self.path == "/sync": return self.send(200, engine.sync())
                if self.path == "/tool": return self.send(200, engine.tool(data["name"], data.get("arguments", {})))
                if self.path == "/shutdown":
                    self.send(200, {"stopping": True})
                    engine.components.stop.set()
                    engine.stopping.set()
                    engine.cancel_sync()
                    engine.cancel_model()
                    if own_group: os.killpg(os.getpgrp(), signal.SIGTERM)
                    else: threading.Thread(target=server.shutdown, daemon=True).start()
                    return
                return self.send(404, {"error": "not_found"})
            except Exception as exc: return self.send(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    info = {"port": server.server_port, "token": token, "pid": os.getpid(), "root": str(ROOT)}
    temp = RUNTIME.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: json.dump(info, f)
    os.chmod(temp, 0o600)
    os.replace(temp, RUNTIME)
    def stop(*_):
        engine.stopping.set()
        engine.cancel_sync()
        engine.cancel_model()
        if engine.model_process and engine.model_process.poll() is None: engine.model_process.terminate()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    threading.Thread(target=engine.watch, daemon=True).start()
    try: server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        engine.stopping.set()
        engine.cancel_sync()
        deadline = time.monotonic() + 5
        while engine.working and time.monotonic() < deadline: time.sleep(0.05)
        if RUNTIME.exists():
            try:
                if json.loads(RUNTIME.read_text()).get("token") == token: RUNTIME.unlink()
            except (OSError, ValueError): pass
        guard.close()

if __name__ == "__main__": main()
