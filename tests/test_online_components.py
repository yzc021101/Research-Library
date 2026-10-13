"""Actual HTTPS download/install tests in an isolated project directory."""
import contextlib,hashlib,http.server,json,os,ssl,subprocess,sys,tempfile,threading,time,unittest.mock,urllib.request,zipfile
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
(BASE/'results/online-install-0.6.3').mkdir(parents=True,exist_ok=True)
root=Path(tempfile.mkdtemp(prefix='online-components-',dir=BASE/'results/online-install-0.6.3'))
os.environ['RESEARCH_LIBRARY_ROOT']=str(root/'library');sys.path.insert(0,str(BASE/'src'))
import components
cert=root/'cert.pem';key=root/'key.pem'
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
payload=root/'payload.zip'
with zipfile.ZipFile(payload,'w') as z:z.writestr('bin/engine',b'isolated component fixture')
body=payload.read_bytes()
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path=='/downgrade':self.send_response(302);self.send_header('Location','http://localhost/file');self.end_headers();return
  self.send_response(200);self.end_headers();self.wfile.write(body if self.path!='/short' else body[:10])
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cert,key);server.socket=ctx.wrap_socket(server.socket,server_side=True)
threading.Thread(target=server.serve_forever,daemon=True).start()
trust=ssl.create_default_context(cafile=str(cert));original=urllib.request.build_opener
item={'id':'ocr','name':'fixture','file':'payload.zip','entry':'bin/engine','download_bytes':len(body),'expanded_bytes':len(b'isolated component fixture'),'sha256':hashlib.sha256(body).hexdigest(),'url':f'https://localhost:{server.server_port}/file'}
checks={}
def wait(m):
 deadline=time.monotonic()+8
 while m.job['phase'] in ('installing','downloading') and time.monotonic()<deadline:time.sleep(.01)
 assert m.job['phase'] not in ('installing','downloading'),m.job
 return m.job
try:
 with unittest.mock.patch.object(components,'catalog',lambda:[item]),unittest.mock.patch.object(urllib.request,'build_opener',lambda *handlers:original(*(h for h in handlers if not isinstance(h,urllib.request.HTTPSHandler)),urllib.request.HTTPSHandler(context=trust))):
  m=components.ComponentManager();m.start('ocr');assert wait(m)['phase']=='complete',m.job
  checks['https_download_and_install']=(components.ROOT/'components/ocr/bin/engine').read_bytes()==b'isolated component fixture'
  assert m.status()['items'][0]['installed'];m.remove('ocr')
  saved=item['sha256'];item['sha256']='0'*64;m.start('ocr');assert wait(m)['phase']=='failed';assert not (components.ROOT/'components/ocr').exists();checks['bad_hash_no_install']=True;item['sha256']=saved
  item['url']=f'https://localhost:{server.server_port}/short';m.start('ocr');assert wait(m)['phase']=='failed';checks['incomplete_download_rejected']=True
  item['url']=f'https://localhost:{server.server_port}/downgrade';m.start('ocr');assert wait(m)['phase']=='failed';checks['http_redirect_rejected']=True
  item['url']='http://localhost/file';m.start('ocr');assert wait(m)['phase']=='failed';checks['http_source_rejected']=True
  item['url']=f'https://localhost:{server.server_port}/file';item['download_bytes']=len(body)-1;m.start('ocr');assert wait(m)['phase']=='failed';checks['oversized_download_rejected']=True;item['download_bytes']=len(body)
  event=threading.Event();event.set()
  try:components.download(item,root/'cancel.zip',event,lambda x:None)
  except InterruptedError:checks['cancelled_download']=True
  else:raise AssertionError('Cancellation failed')
  m.start('ocr');assert wait(m)['phase']=='complete';checks['retry_after_failure']=True;m.remove('ocr')
  with zipfile.ZipFile(root/'unsafe.zip','w') as z:z.writestr('../outside','escaped')
  bad=(root/'unsafe.zip').read_bytes();item.update(sha256=hashlib.sha256(bad).hexdigest(),expanded_bytes=7)
  m.start('ocr',str(root/'unsafe.zip'));assert wait(m)['phase']=='failed';assert not (root/'library/tmp/outside').exists();checks['zip_traversal_rejected']=True
  assert not list((components.ROOT/'tmp').glob('component-*'));checks['temporary_downloads_cleaned']=True
 assert all(checks.values())
 (BASE/'results/online-install-0.6.3/download-checks.json').write_text(json.dumps(checks,indent=2))
 print(json.dumps(checks))
finally:server.shutdown();server.server_close()
