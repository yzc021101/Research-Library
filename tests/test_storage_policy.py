"""Run in a disposable RESEARCH_LIBRARY_ROOT; exercise actual indexed source files."""
import os, sys, json, time, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from paths import ROOT, DATA
from settings import save_settings, load_settings
from library import Library
assert 'storage-test' in str(ROOT) and not (DATA/'library.sqlite3').exists()
source=ROOT/'source';source.mkdir(); f=source/'中文 访谈原文.txt';f.write_text('StorageProbe 800 Gbps',encoding='utf-8')
save_settings({'source_folders':[str(source)],'auto_scan':False})
lib=Library(load_settings);checks={}
lib.sync();hit=lib.search('StorageProbe',mode='keyword')['results'][0]
checks['default_no_snapshot']=not list((DATA/'originals').glob('**/*'))
checks['human_source_citation']=hit['original_path']==str(f) and hit['file_name']==f.name and hit['citation_status']=='current'
did=hit['doc_id'];f.write_text('UpdatedProbe 1600 Gbps',encoding='utf-8')
stale=lib.search('StorageProbe',mode='keyword')['results'][0]
checks['stale_never_links_new_original']=stale['original_path'] is None and bool(stale['citation_warning'])
lib.sync();new=lib.search('UpdatedProbe',mode='keyword')['results'][0]
checks['edit_reindexes']=new['doc_id']!=did and new['citation_status']=='current' and lib.search('StorageProbe',mode='keyword')['count']==0
# Rename uses latest filesystem name, not old document metadata.
g=source/'改名后的访谈.txt';f.rename(g);lib.sync();d=lib.search_documents()['documents'][0]
checks['rename_updates_name']=d['file_name']==g.name and d['original_path']==str(g)
save_settings({'keep_snapshots':True});lib.sync()
snap=lib.db.execute('SELECT snapshot FROM documents WHERE doc_id=?',(d['doc_id'],)).fetchone()[0]
checks['opt_in_snapshot']=Path(snap).name==g.name and (ROOT/snap).is_file()
g.write_text('ThirdProbe 3200 Gbps',encoding='utf-8')
d=lib.search_documents()['documents'][0]
checks['snapshot_matches_old_text']=d['citation_status']=='snapshot' and Path(d['original_path']).name==g.name and '1600' in Path(d['original_path']).read_text()
lib.sync();active=lib.search_documents()['documents'][0]
# Age snapshots; current snapshot retained while enabled, previous versions expire.
oldtime=time.time()-40*86400
for p in (DATA/'originals').rglob('*'):
 if p.is_file():os.utime(p,(oldtime,oldtime))
lib.db.execute("UPDATE documents SET indexed_at='2020-01-01T00:00:00+00:00'");lib.db.commit()
lib.cleanup_storage('expired')
checks['current_snapshot_protected']=(ROOT/lib.db.execute('SELECT snapshot FROM documents WHERE doc_id=?',(active['doc_id'],)).fetchone()[0]).is_file()
checks['old_versions_pruned']=lib.db.execute('SELECT COUNT(*) FROM documents').fetchone()[0]==1
# Regenerable caches only; index, source, model and component stay intact.
for rel in ['data/renders/unit/test.png','cache/office-ocr/a.json','cache/legacy-office/a/result.docx','cache/models/test.onnx','components/ocr/test']:
 p=ROOT/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'probe')
before=g.read_bytes();lib.cleanup_storage('generated')
checks['generated_cleanup_scoped']=not (DATA/'renders/unit/test.png').exists() and (ROOT/'cache/models/test.onnx').exists() and (ROOT/'components/ocr/test').exists() and g.read_bytes()==before
save_settings({'keep_snapshots':False});lib.cleanup_storage('snapshots')
checks['all_snapshots_removed']=not [p for p in (DATA/'originals').rglob('*') if p.is_file()]
checks['text_and_citation_survive_cleanup']=lib.search('ThirdProbe',mode='keyword')['results'][0]['original_path']==str(g)
# Existing hash-named snapshot migration: readable hard link, no content copy.
sha=hashlib.sha256(g.read_bytes()).hexdigest();legacy=DATA/'originals'/(sha+'.txt');legacy.parent.mkdir(exist_ok=True);legacy.write_bytes(g.read_bytes())
lib.db.execute('UPDATE documents SET snapshot=?',(str(legacy.relative_to(ROOT)),));lib.db.commit();g.write_text('FourthProbe',encoding='utf-8')
d=lib.search_documents()['documents'][0];alias=Path(d['original_path'])
checks['legacy_friendly_hardlink']=alias.name==g.name and alias.stat().st_ino==legacy.stat().st_ino
expected=legacy.stat().st_size;checks['hardlinks_not_double_counted']=lib.storage_status()['categories']['snapshots']['bytes']==expected
# Symlink to user source must never be deleted by private-cache clearing.
if os.name!='nt':
 link=DATA/'renders'/'outside';link.parent.mkdir(exist_ok=True);link.symlink_to(source,target_is_directory=True)
 lib.cleanup_storage('generated');checks['symlink_source_untouched']=g.exists()
checks['all_originals_untouched_by_cleanup']=g.read_text()=='FourthProbe'
print(json.dumps({'checks':checks,'passed':sum(checks.values()),'total':len(checks)},ensure_ascii=False,indent=2))
assert all(checks.values()),checks
