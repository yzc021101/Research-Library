"""Keep ONNX/model imports out of the service and reclaim them after idle time."""
import json, os, subprocess, threading
from paths import ROOT, worker_command

class Vector(list):
    def tolist(self): return list(self)

class EmbeddingProcess:
    def __init__(self, model):
        self.lock = threading.Lock()
        with (ROOT/'logs/embedding.log').open('ab') as log:
            self.process = subprocess.Popen(worker_command('embedding_worker', model), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8', bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    def request(self, payload):
        with self.lock:
            if self.process.poll() is not None: raise RuntimeError('模型进程已退出，请重试检索。')
            try:
                self.process.stdin.write(json.dumps(payload)+'\n'); self.process.stdin.flush()
                line = self.process.stdout.readline()
                if not line: raise RuntimeError('模型未返回结果，请检查模型是否完整。')
                result = json.loads(line)
                if 'error' in result: raise RuntimeError(result['error'])
                return [Vector(v) for v in result['vectors']]
            except Exception:
                self.close(); raise
    def query_embed(self, query):
        yield from self.request({'kind':'query', 'query':query})
    def passage_embed(self, texts, batch_size=16):
        yield from self.request({'kind':'passage', 'texts':list(texts)})
    def close(self):
        if self.process.stdin and not self.process.stdin.closed: self.process.stdin.close()
        try: self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()
        if self.process.stdout: self.process.stdout.close()
    def __del__(self):
        try: self.close()
        except Exception: pass
