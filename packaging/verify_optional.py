from pathlib import Path
import json, os, shutil, subprocess, sys, time, urllib.request, hashlib
engine=Path(sys.argv[1]).resolve();root=Path(sys.argv[2]).resolve();packs=Path(sys.argv[3]).resolve();fixtures=Path(sys.argv[4]).resolve();models=Path(sys.argv[5]).resolve();report=Path(sys.argv[6]).resolve()
assert 'packag' in str(root).lower() and not root.exists()
root.mkdir(parents=True);(root/'inbox').mkdir();(root/'data').mkdir();(root/'logs').mkdir()
(root/'data/settings.json').write_text(json.dumps({'source_folders':[str(root/'inbox')],'app_managed':True,'auto_scan':False}),encoding='utf-8')
env={**os.environ,'RESEARCH_LIBRARY_ROOT':str(root),'PYTHONUTF8':'1','PATH':os.environ.get('SystemRoot','C:/Windows')+'/System32' if os.name=='nt' else '/usr/bin:/bin:/usr/sbin:/sbin'}
proc=None;log=(root/'logs/test.log').open('wb');checks={}
def req(route,data=None):
 info=json.loads((root/'data/service.json').read_text(encoding='utf-8'))
 r=urllib.request.Request('http://127.0.0.1:'+str(info['port'])+route,data=json.dumps(data).encode() if data is not None else None,headers={'Authorization':'Bearer '+info['token'],'Content-Type':'application/json'})
 with urllib.request.urlopen(r,timeout=240) as response:return json.load(response)
def start():
 global proc
 proc=subprocess.Popen([str(engine),'backend'],env=env,stdout=log,stderr=log,cwd=root)
 for _ in range(150):
  try:return req('/status')
  except Exception:time.sleep(.2)
 raise RuntimeError('start failed')
def stop():
 if proc and proc.poll() is None:req('/shutdown',{});proc.wait(timeout=30)
def wait_job(kind,timeout=240):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  s=req('/status');job=s['components']['job'] if kind=='components' else s['model_job']
  if job['phase'] in ('complete','failed','cancelled'):return job
  time.sleep(.5)
 raise TimeoutError(kind)
try:
 status=start();items=status['components']['items'];assert len(items)==2
 # Wrong files are rejected, never unpacked or run.
 bad=root/'bad.zip';bad.write_text('not a zip')
 req('/components/install',{'id':'ocr','path':str(bad)});job=wait_job('components');checks['reject_bad_checksum']=job['phase']=='failed' and not (root/'components/ocr').exists()
 for item in items:
  req('/components/install',{'id':item['id'],'path':str(packs/item['file'])});job=wait_job('components');assert job['phase']=='complete',job
 checks['both_components_installed']=all(i['installed'] for i in req('/status')['components']['items'])
 stop();start()
 for p in fixtures.iterdir():
  if p.suffix in ('.doc','.ppt','.xls'):shutil.copy2(p,root/'inbox'/p.name)
 req('/tool',{'name':'sync_library','arguments':{}});status=req('/status')
 checks['three_legacy_formats']=status['active_documents']==3
 assert checks['three_legacy_formats'], {'active_documents':status['active_documents'],'last_error':status.get('last_error')}
 hits=req('/tool',{'name':'search_passages','arguments':{'query':'800 Gbps','mode':'keyword','top_k':20}})
 checks['ocr_hits']=any('tesseract' in h['extraction_method'] for h in hits['results'])
 assert checks['ocr_hits'], 'No OCR result from legacy fixtures'
 # Seed an existing unmodified model cache into this test-only directory to validate the
 # frozen model subprocess, ONNX inference and LanceDB without a repeated 250 MB download.
 stop()
 mid='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2';key=hashlib.sha256(mid.encode()).hexdigest()[:16]
 target=root/'cache/model-packages'/key;shutil.copytree(models,target,symlinks=False)
 (root/'data/model-assets').mkdir(exist_ok=True);(root/'data/model-assets'/(key+'.json')).write_text(json.dumps({'model':mid,'validated':True}))
 start();req('/models/switch',{'model':mid});job=wait_job('models');assert job['phase']=='complete',job
 semantic=req('/tool',{'name':'search_passages','arguments':{'query':'800 Gbps','mode':'semantic'}})
 checks['frozen_model_worker_semantic']=semantic['count']>0 and semantic['mode']=='semantic'
 req('/models/remove',{'model':mid});checks['remove_model']=not target.exists()
 checks['fallback_after_removal']=req('/tool',{'name':'search_passages','arguments':{'query':'800 Gbps','mode':'hybrid'}})['mode']=='keyword'
 for item in items:req('/components/remove',{'id':item['id']})
 checks['remove_components']=all(not i['installed'] for i in req('/status')['components']['items'])
 checks['text_survives_component_removal']=req('/tool',{'name':'search_passages','arguments':{'query':'800 Gbps','mode':'keyword'}})['count']>0
finally:
 stop();log.close()
report.write_text(json.dumps({'checks':checks,'passed':sum(checks.values()),'total':len(checks)},ensure_ascii=False,indent=2),encoding='utf-8');print(report.read_text(encoding='utf-8'));assert all(checks.values()),checks
