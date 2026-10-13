from pathlib import Path
import os,sys,json,subprocess,time,urllib.request
engine=Path(sys.argv[1]).resolve();root=Path(sys.argv[2]).resolve();out=Path(sys.argv[3]).resolve()
assert 'storage-test' in str(root) and not root.exists()
(root/'inbox').mkdir(parents=True);(root/'data').mkdir()
f=root/'inbox'/'真实中文 文件名.txt';f.write_text('ReleaseStorage 800 Gbps',encoding='utf-8')
(root/'data/settings.json').write_text(json.dumps({'source_folders':[str(f.parent)],'auto_scan':False,'app_managed':True}))
env={**os.environ,'RESEARCH_LIBRARY_ROOT':str(root),'PYTHONUTF8':'1'}
log=(root/'engine.log').open('wb');p=subprocess.Popen([str(engine),'backend'],env=env,stdout=log,stderr=log)
def req(path,data=None):
 state=json.loads((root/'data/service.json').read_text())
 r=urllib.request.Request('http://127.0.0.1:'+str(state['port'])+path,data=json.dumps(data).encode() if data is not None else None,headers={'Authorization':'Bearer '+state['token'],'Content-Type':'application/json'})
 with urllib.request.urlopen(r,timeout=120) as q:return json.load(q)
def tool(name,args={}):return req('/tool',{'name':name,'arguments':args})
checks={}
try:
 for _ in range(150):
  try:req('/status');break
  except Exception:
   if p.poll() is not None:raise RuntimeError((root/'engine.log').read_text())
   time.sleep(.2)
 tool('sync_library');h=tool('search_passages',{'query':'ReleaseStorage','mode':'keyword'})['results'][0]
 checks['citation_actual_filename']=h['original_path']==str(f) and h['file_name']==f.name
 checks['no_copies_by_default']=req('/storage/status',{})['categories']['snapshots']['bytes']==0
 f.write_text('ReleaseChanged 1600 Gbps',encoding='utf-8');h=tool('search_passages',{'query':'ReleaseStorage','mode':'keyword'})['results'][0]
 checks['changed_source_warning']=h['original_path'] is None and bool(h['citation_warning'])
 tool('sync_library');req('/settings',{'keep_snapshots':True,'cache_retention_days':7});tool('sync_library')
 checks['snapshot_setting_persists']=req('/settings')['keep_snapshots'] and req('/storage/status',{})['categories']['snapshots']['bytes']>0
 f.write_text('ReleaseFinal 3200 Gbps',encoding='utf-8');h=tool('search_passages',{'query':'ReleaseChanged','mode':'keyword'})['results'][0]
 checks['friendly_snapshot_fallback']=h['citation_status']=='snapshot' and Path(h['original_path']).name==f.name
 req('/settings',{'keep_snapshots':False});req('/storage/cleanup',{'mode':'snapshots'});tool('sync_library')
 for rel in ['data/renders/test/a.png','cache/office-ocr/a.json','cache/legacy-office/test/result.docx']:
  q=root/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_text('cache')
 r=req('/storage/cleanup',{'mode':'generated'});checks['cleanup_api']=r['removed_files']==3 and not r['errors']
 h=tool('search_passages',{'query':'ReleaseFinal','mode':'keyword'})['results'][0]
 checks['source_and_index_preserved']=h['original_path']==str(f) and f.read_text()=='ReleaseFinal 3200 Gbps'
 checks['snapshot_removed']=req('/storage/status',{})['categories']['snapshots']['bytes']==0
 probe=subprocess.run([str(engine),'check_mcp'],env=env,capture_output=True,text=True,timeout=60)
 checks['mcp_handshake']=probe.returncode==0 and json.loads(probe.stdout)['tool_count']==7
finally:
 try:req('/shutdown',{})
 except Exception:pass
 p.wait(timeout=30);log.close()
out.write_text(json.dumps({'checks':checks,'passed':sum(checks.values()),'total':len(checks)},ensure_ascii=False,indent=2),encoding='utf-8');print(out.read_text())
assert all(checks.values()),checks
