from paths import ROOT
import json
import logging
import urllib.request
import urllib.error

class BackendProxy:
    def request(self, path, payload=None):
        try:
            info = json.loads((ROOT / "data/service.json").read_text())
            request = urllib.request.Request(
                f'http://127.0.0.1:{int(info["port"])}{path}',
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"Authorization": "Bearer " + info["token"], "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(json.loads(exc.read()).get("error", str(exc))) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, PermissionError):
                raise RuntimeError("当前调用环境禁止连接本机服务；需要允许本机连接，这不表示资料库服务已停止。") from exc
            raise RuntimeError("本地资料库服务连接失败。请检查 App 的运行状态。") from exc
        except (OSError, ValueError, KeyError) as exc:
            logging.exception("Local backend request failed")
            raise RuntimeError("本地资料库服务未运行。请打开 投研纵览 App，在菜单栏点击‘启动服务’。") from exc

    def status(self): return self.request("/status")
    def tool(self, name, **arguments): return self.request("/tool", {"name": name, "arguments": arguments})
    def sync(self): return self.tool("sync_library")
    def search_documents(self, query="", **args): return self.tool("search_documents", query=query, **args)
    def search(self, query, top_k=None, mode=None, **args): return self.tool("search_passages", query=query, top_k=top_k, mode=mode, **args)
    def read_document(self, doc_id, start_page=1, end_page=None): return self.tool("read_document", doc_id=doc_id, start_page=start_page, end_page=end_page)
    def read_unit(self, doc_id, unit_index): return self.tool("read_unit", doc_id=doc_id, unit_index=unit_index)
    def read_page(self, doc_id, pdf_page, render=False): return self.tool("read_page", doc_id=doc_id, pdf_page=pdf_page, render=render)
