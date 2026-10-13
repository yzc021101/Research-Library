import sys,os,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from paths import ROOT,DATA
from settings import save_settings,load_settings
from library import Library
import pymupdf
assert 'storage-test' in str(ROOT) and not (DATA/'library.sqlite3').exists()
f=ROOT/'inbox'/'报告.pdf'
def write(text):
 pdf=pymupdf.open();p=pdf.new_page();p.insert_text((30,30),text);pdf.save(f);pdf.close()
write('BeforePDF 800 Gbps. This is a native text report with stable page locations.')
save_settings({'source_folders':[str(f.parent)],'auto_scan':False});l=Library(load_settings);l.sync();d=l.search_documents()['documents'][0];did=d['doc_id']
r=l.read_page(did,1,True);assert Path(r['image_path']).exists()
f.unlink();write('AfterPDF 1600 Gbps. A changed native text report with updated information.')
try:l.read_page(did,1)
except ValueError as e:assert '修改' in str(e)
else:raise AssertionError('stale PDF rendered as old version')
l.sync();save_settings({'keep_snapshots':True});l.sync();d=l.search_documents()['documents'][0];did=d['doc_id']
f.unlink();write('ThirdPDF 3200 Gbps. A third version of the native report with additional information.')
r=l.read_page(did,1,True);assert r['document']['citation_status']=='snapshot' and 'AfterPDF' in r['pages'][0]['text'] and Path(r['document']['original_path']).name=='报告.pdf'
print(json.dumps({'current_pdf_rendered':True,'changed_pdf_blocked_without_snapshot':True,'snapshot_pdf_matches_old_text':True}))
