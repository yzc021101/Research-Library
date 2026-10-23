"""Targeted retries must preserve successful records, handle removals, and release idle models safely."""
from pathlib import Path
import tempfile, os, sys, unittest, time, threading
from unittest.mock import patch
base=Path(__file__).resolve().parents[1];sys.path.insert(0,str(base/'src'))
fixture=tempfile.TemporaryDirectory();os.environ['RESEARCH_LIBRARY_ROOT']=fixture.name
import library
from library import Library
from paths import INBOX
class RetryTests(unittest.TestCase):
 def setUp(self):
  self.lib=Library(lambda:{'source_folders':[str(INBOX)],'keep_snapshots':False,'search_mode':'keyword'})
  self.good=INBOX/'good.txt';self.bad=INBOX/'bad.txt';self.other=INBOX/'other.txt'
  for p in [self.good,self.bad,self.other]:p.write_text('ResearchRetryAnchor '+p.stem)
  extract=self.lib.extract
  def fail(path,doc):
   if path!=self.good:raise ValueError('temporary reader error')
   return extract(path,doc)
  with patch.object(self.lib,'extract',side_effect=fail):self.lib.sync()
 def tearDown(self):
  self.lib.db.close()
  for p in INBOX.glob('*'):p.unlink()
  import paths
  for p in paths.DATA.glob('*.sqlite*'):p.unlink()
 def test_single_and_all(self):
  before=dict(self.lib.db.execute('SELECT * FROM sources WHERE path=?',(str(self.good),)).fetchone())
  result=self.lib.sync(retry=True,path=str(self.bad))
  self.assertEqual([x['file'] for x in result['results']],[str(self.bad)])
  self.assertEqual(dict(self.lib.db.execute('SELECT * FROM sources WHERE path=?',(str(self.good),)).fetchone()),before)
  self.assertEqual(self.lib.db.execute('SELECT state FROM sources WHERE path=?',(str(self.other),)).fetchone()[0],'failed')
  result=self.lib.sync(retry=True);self.assertEqual([x['file'] for x in result['results']],[str(self.other)])
  self.assertEqual(len(self.lib.active_docs()),3)
 def test_removed_and_invalid(self):
  self.bad.unlink();self.lib.sync(retry=True)
  self.assertEqual(self.lib.db.execute('SELECT state FROM sources WHERE path=?',(str(self.bad),)).fetchone()[0],'missing')
  self.assertEqual(self.lib.db.execute('SELECT state FROM sources WHERE path=?',(str(self.good),)).fetchone()[0],'ready')
  with self.assertRaises(ValueError):self.lib.sync(retry=True,path='/not/configured/file.txt')
 def test_cancelled_retry_preserves_sources(self):
  self.lib.sync_cancel.set();result=self.lib.sync(prepared=True,retry=True)
  self.assertTrue(result['cancelled']);self.assertEqual(len(result['results']),0)
  self.assertEqual(self.lib.db.execute("SELECT count(*) FROM sources WHERE state='missing'").fetchone()[0],0)
 def test_idle_model_release_and_reload(self):
  self.lib._embedder=object();self.lib._embedding_last_used=time.monotonic()
  self.assertFalse(self.lib.release_idle_model())
  self.lib._embedding_last_used=0;self.assertTrue(self.lib.release_idle_model());self.assertIsNone(self.lib._embedder)
  model=object()
  with patch.object(library,'create_embedder',return_value=model) as create:
   self.assertIs(self.lib.embedder(),model);self.assertIs(self.lib.embedder(),model);create.assert_called_once()
 def test_model_not_released_during_operation(self):
  self.lib._embedder=object();self.lib._embedding_last_used=0;result=[]
  with self.lib.lock:
   t=threading.Thread(target=lambda:result.append(self.lib.release_idle_model()));t.start();t.join(2)
  self.assertEqual(result,[False]);self.assertIsNotNone(self.lib._embedder)
 def test_partial_remains_searchable_and_is_retryable(self):
  import json
  self.lib.sync(retry=True)
  doc=self.lib.db.execute('SELECT doc_id FROM sources WHERE path=?',(str(self.bad),)).fetchone()[0]
  meta=json.loads(self.lib.db.execute('SELECT metadata FROM documents WHERE doc_id=?',(doc,)).fetchone()[0])
  meta.update(partial=True,extraction_warnings=['部分入库：图片未识别'])
  self.lib.db.execute('UPDATE documents SET metadata=? WHERE doc_id=?',(json.dumps(meta),doc))
  self.lib.db.execute("UPDATE sources SET state='partial' WHERE doc_id=?",(doc,));self.lib.db.commit()
  self.assertIn(doc,self.lib.active_docs())
  result=self.lib.sync(retry=True,path=str(self.bad))
  self.assertEqual([x['file'] for x in result['results']],[str(self.bad)])
  self.assertEqual(result['results'][0]['action'],'indexed')
  self.assertEqual(self.lib.db.execute('SELECT state FROM sources WHERE doc_id=?',(doc,)).fetchone()[0],'ready')
 def test_old_partial_records_migrate_without_reparse(self):
  import json
  doc=self.lib.db.execute('SELECT doc_id FROM sources WHERE path=?',(str(self.good),)).fetchone()[0]
  meta=json.loads(self.lib.db.execute('SELECT metadata FROM documents WHERE doc_id=?',(doc,)).fetchone()[0])
  meta.update(partial=True,extraction_warnings=['部分入库：图片未识别'])
  self.lib.db.execute('UPDATE documents SET metadata=? WHERE doc_id=?',(json.dumps(meta),doc));self.lib.db.commit()
  self.lib.db.close();self.lib=Library(lambda:{'source_folders':[str(INBOX)]})
  self.assertEqual(self.lib.db.execute('SELECT state FROM sources WHERE doc_id=?',(doc,)).fetchone()[0],'partial')
  self.assertIn(doc,self.lib.active_docs())
if __name__=='__main__':unittest.main()
