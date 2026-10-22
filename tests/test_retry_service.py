"""HTTP black-box retry workflow against a bundled engine, using disposable files."""
from pathlib import Path
import json, os, subprocess, sys, time, urllib.request
from docx import Document
engine=Path(sys.argv[1]).resolve();root=Path(sys.argv[2]).resolve()
assert not root.exists(), 'Test directory must be new'
for name in ['data','inbox','logs']: (root/name).mkdir(parents=True,exist_ok=True)
settings={'source_folders':[str(root/'inbox')],'auto_scan':False,'app_managed':True,'search_mode':'keyword'}
(root/'data/settings.json').write_text(json.dumps(settings))
(root/'inbox/good.txt').write_text('PreservedSuccessfulFile')
for name in ['single.docx','all.docx']:(root/'inbox'/name).write_text('broken document')
def req(route,body=None):
 state=json.loads((root/'data/service.json').read_text())
 request=urllib.request.Request(f"http://127.0.0.1:{state['port']}"+route,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+state['token'],'Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
def wait():
 for _ in range(300):
  s=req('/status')
  if not s['busy']:return s
  time.sleep(.1)
 raise TimeoutError('retry did not finish')
log=(root/'logs/backend.log').open('wb');env={**os.environ,'RESEARCH_LIBRARY_ROOT':str(root)}
p=subprocess.Popen([str(engine),'backend'],env=env,stdout=log,stderr=log)
try:
 for _ in range(150):
  try:req('/status');break
  except Exception:time.sleep(.2)
 else:raise TimeoutError('backend start')
 req('/sync',{});status=wait();assert len([x for x in status['sources'] if x['state']=='failed'])==2
 good=next(x for x in status['sources'] if x['path'].endswith('good.txt'))
 for name in ['single.docx','all.docx']:
  d=Document();d.add_paragraph('RecoveredResearchContent '+name);d.save(root/'inbox'/name)
 assert req('/imports/retry',{'path':str(root/'inbox/single.docx')})['accepted'];status=wait()
 assert len([x for x in status['sources'] if x['state']=='failed'])==1
 assert next(x for x in status['sources'] if x['path'].endswith('good.txt'))==good
 assert req('/imports/retry',{})['accepted'];status=wait();assert all(x['state']=='ready' for x in status['sources'])
 assert len(status['sources'])==3
 print(json.dumps({'failed_initial':2,'single_retry':True,'retry_all':True,'successful_file_unchanged':True,'final_ready':3}))
finally:
 try:req('/shutdown',{})
 except Exception:pass
 try:p.wait(timeout=10)
 except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=10)
 log.close()
