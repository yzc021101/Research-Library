"""Updater trust boundaries; no live application or network changes."""
import importlib, io, json, os, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))

class UpdaterTests(unittest.TestCase):
 def setUp(self):
  base=Path(__file__).resolve().parents[1]/'build/update-tests';base.mkdir(parents=True,exist_ok=True)
  self.tmp=tempfile.TemporaryDirectory(dir=base);os.environ['RESEARCH_LIBRARY_ROOT']=self.tmp.name
  for n in ['paths','components','updater']:sys.modules.pop(n,None)
  self.u=importlib.import_module('updater');self.u.HOME.mkdir()
 def tearDown(self):self.tmp.cleanup()
 def release(self,tag='v0.6.7'):
  u=self.u;n=u.asset_name()
  return {'tag_name':tag,'assets':[{'name':n,'state':'uploaded','browser_download_url':u.REPO+'/releases/download/'+tag+'/'+n,'digest':'sha256:'+'a'*64,'size':20}]}
 def test_numeric_versions(self):
  self.assertGreater(self.u.version('0.10.0'),self.u.version('0.9.9'))
  for v in ['v1.2.3-beta','../foo','1.2','1.2.3\n']:
   with self.assertRaises(ValueError):self.u.version(v)
 def test_release_trust(self):
  self.assertEqual(self.u.release_asset(self.release())['version'],'0.6.7')
  for key,val in [('browser_download_url','https://example.com/a'),('digest',''),('size',-1)]:
   d=self.release();d['assets'][0][key]=val
   with self.assertRaises(ValueError):self.u.release_asset(d)
  d=self.release();d['prerelease']=True
  with self.assertRaises(ValueError):self.u.release_asset(d)
 def test_no_downgrade(self):
  with patch.object(self.u,'fetch_release',return_value=self.release('v0.6.3')):
   self.assertEqual(self.u.check('0.6.7')['phase'],'current')
 def test_available_and_daily_throttle(self):
  with patch.object(self.u,'fetch_release',return_value=self.release()) as fetch:
   self.assertEqual(self.u.check('0.6.3')['phase'],'available');self.u.check('0.6.3',True);self.assertEqual(fetch.call_count,1)
 def test_bad_checksum(self):
  path=self.u.HOME/'file';path.write_bytes(b'0'*20)
  with self.assertRaises(ValueError):self.u.verify_archive(path,self.u.release_asset(self.release()))
 def test_unsafe_archive(self):
  for name in ['../escape','research_library/../../escape','/abs','research_library/C:evil','research_library\\..\\..\\escape']:
   z=self.u.HOME/'test.zip'
   with zipfile.ZipFile(z,'w') as out:
    info=zipfile.ZipInfo('placeholder');info.filename=name;out.writestr(info,'bad')
   with self.assertRaises(ValueError,msg=name):self.u.extract_zip(z,self.u.HOME/'unpack')
   self.assertFalse((self.u.HOME/'escape').exists())
 def test_update_lock(self):
  with self.u.lock():
   with self.assertRaises(RuntimeError):
    with self.u.lock():pass
 def test_cancel(self):
  (self.u.HOME/'cancel').touch()
  with self.assertRaises(InterruptedError):self.u.cancelled()
 def test_failed_prepare_preserves_target(self):
  target=Path(self.tmp.name)/'app';target.mkdir();(target/'sentinel').write_text('original')
  with patch.object(self.u,'validate_app',return_value='0.6.3'),patch.object(self.u,'fetch_release',return_value=self.release()):
   with self.assertRaises(ValueError):self.u.prepare(target)
  self.assertEqual((target/'sentinel').read_text(),'original')
 def test_invalid_json_ignored(self):
  self.u.STATE.write_text('{bad');self.assertEqual(self.u.read(self.u.STATE),{})
 def test_busy_state_file_retried_atomically(self):
  self.u.write(self.u.STATE,{'phase':'old'})
  replace=self.u.os.replace;calls=[]
  def busy_then_replace(src,dst):
   calls.append(1)
   if len(calls)<3:
    self.assertEqual(self.u.read(self.u.STATE),{'phase':'old'})
    raise PermissionError('Sharing violation')
   return replace(src,dst)
  with patch.object(self.u.os,'replace',side_effect=busy_then_replace),patch.object(self.u.time,'sleep'):
   self.u.write(self.u.STATE,{'phase':'ready'})
  self.assertEqual(self.u.read(self.u.STATE),{'phase':'ready'})
  self.assertEqual(len(calls),3);self.assertFalse(list(self.u.HOME.glob('*.tmp')))
 def test_persistent_write_failure_preserves_previous_state(self):
  self.u.write(self.u.STATE,{'phase':'old'})
  with patch.object(self.u.os,'replace',side_effect=PermissionError('Denied')) as replace,patch.object(self.u.time,'sleep'):
   with self.assertRaises(PermissionError):self.u.write(self.u.STATE,{'phase':'ready'})
  self.assertEqual(replace.call_count,20)
  self.assertEqual(self.u.read(self.u.STATE),{'phase':'old'})
  self.assertFalse(list(self.u.HOME.glob('*.tmp')))

if __name__=='__main__':unittest.main()
