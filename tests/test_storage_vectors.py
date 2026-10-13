import os,sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from paths import ROOT,DATA
from settings import save_settings,load_settings
from library import Library
assert 'storage-test' in str(ROOT) and not (DATA/'library.sqlite3').exists()
f=ROOT/'inbox'/'probe.txt';f.write_text('BeforeVector');save_settings({'source_folders':[str(f.parent)]})
l=Library(load_settings);l.sync();old=l.search_documents()['documents'][0]['doc_id'];f.write_text('AfterVector');l.sync();new=l.search_documents()['documents'][0]['doc_id']
t=l.vector_table();dim=l.embedding.get('dimensions',384)
t.add([{'chunk_id':x+':p1:c1','doc_id':x,'vector':[0.1]*dim} for x in [old,new]])
l.db.execute("UPDATE documents SET indexed_at='2020-01-01T00:00:00+00:00' WHERE doc_id=?",(old,));l.db.commit()
r=l.cleanup_storage('expired');assert not r['errors'],r['errors'];assert l.vectors().open_table(l.embedding["table"]).count_rows()==1;assert l.search('AfterVector',mode='keyword')['count']==1
print(json.dumps({'expired_vector_removed':True,'current_vector_preserved':True,'compaction_succeeded':True}))
