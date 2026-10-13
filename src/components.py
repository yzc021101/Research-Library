"""Optional, checksum-pinned component packs. Never edits a system installation."""
from paths import ROOT
from pathlib import Path, PurePosixPath
import hashlib, json, os, shutil, stat, sys, tempfile, threading, urllib.request, urllib.parse, zipfile, ssl
import certifi

def bytes_used(folder):
    if not folder.exists(): return 0
    return sum(p.stat().st_size for p in folder.rglob('*') if p.is_file() and not p.is_symlink())

def catalog():
    path = Path(sys.executable).parent/'components.json' if getattr(sys,'frozen',False) else Path(__file__).parents[1]/'packaging/components.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []

class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('组件下载不允许跳转到非 HTTPS 地址')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def download(item, archive, stop, progress):
    url=urllib.parse.urlsplit(item['url'])
    if url.scheme!='https' or not url.hostname or url.username or url.password:
        raise ValueError('组件下载必须使用不含凭据的 HTTPS 地址')
    request=urllib.request.Request(item['url'], headers={'User-Agent':'research_library/0.6.3'})
    with urllib.request.build_opener(HTTPSOnly(), urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where()))).open(request,timeout=30) as response, archive.open('wb') as out:
        if urllib.parse.urlsplit(response.geturl()).scheme!='https': raise ValueError('下载地址不安全')
        count=0
        while data:=response.read(1024*1024):
            if stop.is_set(): raise InterruptedError('安装已取消')
            count+=len(data)
            if count>item['download_bytes']: raise ValueError('下载超出预期大小')
            out.write(data);progress(count)
        if count!=item['download_bytes']: raise ValueError('下载不完整，请重试')

class ComponentManager:
    def __init__(self):
        self.lock=threading.Lock();self.job={'phase':'idle'};self.stop=threading.Event()
        self.sizes={}
    def status(self):
        result=[]
        for item in catalog():
            folder=ROOT/'components'/item['id']
            installed=(folder/item['entry']).is_file()
            external=False
            if not installed:
                if item['id']=='legacy-office':
                    try:
                        from legacy_office import converter
                        converter();external=True
                    except RuntimeError: pass
                elif item['id']=='ocr': external=bool(shutil.which('tesseract'))
            result.append({**item,'installed':installed,'external':external,'installed_bytes':self.sizes.get(item['id'],item.get('expanded_bytes',0)) if installed else 0})
        return {'items':result,'job':dict(self.job)}
    def start(self, component, path=None):
        item=next((x for x in catalog() if x['id']==component),None)
        if not item: raise ValueError('未知组件')
        if (ROOT/'components'/component).exists(): raise ValueError('组件已安装；如需重装请先移除。')
        with self.lock:
            if self.job['phase'] in ('downloading','installing'): raise ValueError('已有组件安装任务')
            if not path and not item.get('url'): raise ValueError('此构建尚未连接发布仓库。请使用发布者提供的联网发行版，或导入配套组件 ZIP。')
            self.stop.clear();self.job={'phase':'installing' if path else 'downloading','id':component,'done':0,'total':item.get('download_bytes',0)}
        def work():
            try:
                with tempfile.TemporaryDirectory(prefix='component-',dir=ROOT/'tmp') as tmp:
                    temp=Path(tmp);archive=Path(path) if path else temp/'download.zip'
                    if not path:
                        download(item,archive,self.stop,lambda count:self.job.update(done=count))
                    h=hashlib.sha256()
                    with archive.open('rb') as stream:
                        while data:=stream.read(1024*1024):
                            if self.stop.is_set(): raise InterruptedError('安装已取消')
                            h.update(data)
                    if h.hexdigest()!=item['sha256']: raise ValueError('组件校验失败，请使用与此版本配套的原始组件包。')
                    if shutil.disk_usage(temp).free<item['expanded_bytes']+16*1024*1024: raise ValueError('剩余磁盘空间不足，未安装组件')
                    self.job['phase']='installing';target=temp/'unpacked';target.mkdir()
                    links=[]
                    with zipfile.ZipFile(archive) as z:
                        if sum(i.file_size for i in z.infolist())>item['expanded_bytes']+1024: raise ValueError('组件解压大小异常')
                        for i in z.infolist():
                            if self.stop.is_set(): raise InterruptedError('安装已取消')
                            part=PurePosixPath(i.filename)
                            if part.is_absolute() or '..' in part.parts or '\\' in i.filename or ':' in i.filename: raise ValueError('不安全的组件路径')
                            dest=target.joinpath(*part.parts)
                            if stat.S_ISLNK(i.external_attr>>16):
                                link=z.read(i).decode('utf-8')
                                if os.name=='nt' or Path(link).is_absolute() or not (dest.parent/link).resolve().is_relative_to(target.resolve()): raise ValueError('不安全的组件链接')
                                links.append((dest,link));continue
                            if i.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
                            dest.parent.mkdir(parents=True,exist_ok=True)
                            with z.open(i) as inp,dest.open('wb') as out: shutil.copyfileobj(inp,out)
                            if os.name!='nt':dest.chmod(0o755 if i.external_attr>>16&0o111 else 0o644)
                    for dest,link in links:
                        dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to(link)
                    for dest,link in links:
                        if not dest.resolve().is_relative_to(target.resolve()):raise ValueError('组件链接越界')
                    if not (target/item['entry']).is_file(): raise ValueError('组件缺少启动文件')
                    if self.stop.is_set(): raise InterruptedError('安装已取消')
                    target.rename(ROOT/'components'/component)
                    self.sizes[component]=item['expanded_bytes']
                    self.job={'phase':'complete','id':component,'message':'安装完成。请重启服务后重新同步资料。'}
            except Exception as exc:self.job={'phase':'cancelled' if isinstance(exc,InterruptedError) else 'failed','id':component,'error':str(exc)}
        threading.Thread(target=work,daemon=True).start()
        return {'accepted':True}
    def remove(self,component):
        if component not in {x['id'] for x in catalog()}:raise ValueError('未知组件')
        if self.job['phase'] in ('downloading','installing'):raise ValueError('请等待组件安装结束')
        folder=ROOT/'components'/component
        if folder.is_symlink():raise ValueError('组件路径不能是符号链接')
        if folder.exists():shutil.rmtree(folder)
        self.job={'phase':'complete','message':'已移除本应用的组件。请重启服务以更新状态。'}
        return {'removed':True}
