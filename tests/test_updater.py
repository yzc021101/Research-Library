"""Updater trust boundaries; no live application or network changes."""
import importlib, io, json, os, tempfile, unittest, zipfile, hashlib
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
 def release(self,tag='v0.6.8'):
  u=self.u;n=u.asset_name()
  return {'tag_name':tag,'assets':[{'name':n,'state':'uploaded','browser_download_url':u.REPO+'/releases/download/'+tag+'/'+n,'digest':'sha256:'+'a'*64,'size':20}]}
 def cached_release(self,tag='v0.6.9'):
  u=self.u;data=self.release(tag);payload=tag.encode()*12
  data['assets'][0].update(size=len(payload),digest='sha256:'+hashlib.sha256(payload).hexdigest())
  item=u.release_asset(data);(u.HOME/item['name']).write_bytes(payload)
  u.state(phase='ready',release=item,current='0.6.8',done=len(payload),total=len(payload),error='')
  return data,item,payload
 def transaction(self,release_version='0.6.8',result=True,identified=False):
  u=self.u;target=Path(self.tmp.name)/'app';target.mkdir(exist_ok=True)
  stage=target.parent/('.research-library-update-'+'a'*32);stage.mkdir(exist_ok=True)
  backup=target.parent/('.research-library-previous-'+'b'*32);backup.mkdir(exist_ok=True)
  journal={'target':str(target),'stage':str(stage),'backup':str(backup),'unpacked':str(stage/'app'),'version':release_version,'archive':str(u.HOME/u.asset_name())}
  outcome={'ok':result}
  if identified:journal['id']='c'*32;outcome['id']=journal['id']
  u.write(u.HOME/'transaction.json',journal);u.write(u.HOME/'install-result.json',outcome)
  return target,journal
 def test_download_progress_and_verification(self):
  u=self.u;payload=b'x'*(2*1024*1024+7);release=self.release();item=release['assets'][0]
  item['size']=len(payload);item['digest']='sha256:'+hashlib.sha256(payload).hexdigest()
  history=[];original=u.state
  def record(**changes):
   result=original(**changes);history.append(dict(result));return result
  class FakeOpener:
   def open(self,*a,**k):return io.BytesIO(payload)
  with patch.object(u,'fetch_release',return_value=release),patch.object(u,'opener',return_value=FakeOpener()),patch.object(u,'state',side_effect=record):
   result=u.download('0.0.1')
  self.assertEqual(result['phase'],'ready');self.assertEqual(result['done'],len(payload));self.assertEqual(result['total'],len(payload))
  self.assertEqual([x['phase'] for x in history if x['phase']!='downloading'],['verifying','ready'])
  counts=[x['done'] for x in history];self.assertEqual(counts,sorted(counts))
  self.assertEqual((u.HOME/u.asset_name()).read_bytes(),payload)
  self.assertFalse(list(u.HOME.glob('*.part')))
 def test_numeric_versions(self):
  self.assertGreater(self.u.version('0.10.0'),self.u.version('0.9.9'))
  for v in ['v1.2.3-beta','../foo','1.2','1.2.3\n']:
   with self.assertRaises(ValueError):self.u.version(v)
 def test_release_trust(self):
  self.assertEqual(self.u.release_asset(self.release())['version'],'0.6.8')
  for key,val in [('browser_download_url','https://example.com/a'),('digest',''),('size',-1)]:
   d=self.release();d['assets'][0][key]=val
   with self.assertRaises(ValueError):self.u.release_asset(d)
  d=self.release();d['prerelease']=True
  with self.assertRaises(ValueError):self.u.release_asset(d)
 def test_no_downgrade(self):
  with patch.object(self.u,'fetch_release',return_value=self.release('v0.6.3')):
   self.assertEqual(self.u.check('0.6.8')['phase'],'current')
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
 def test_finished_legacy_install_cannot_erase_newer_download_on_restart(self):
  u=self.u;_,item,payload=self.cached_release();target,journal=self.transaction()
  before=u.read(u.STATE)
  with patch.object(u,'validate_app',return_value='0.6.8'),patch.object(u,'fetch_release',side_effect=AssertionError('Restart must work offline')):
   u.finish(target)
   self.assertEqual(u.read(u.STATE),before)
   u.finish(target) # A second fresh launch cannot replay the old completion.
  self.assertEqual((u.HOME/item['name']).read_bytes(),payload)
  self.assertFalse((u.HOME/'transaction.json').exists());self.assertFalse((u.HOME/'install-result.json').exists())
  self.assertFalse(Path(journal['backup']).exists());self.assertFalse(Path(journal['stage']).exists())
 def test_failed_old_install_cannot_erase_newer_download(self):
  u=self.u;_,item,payload=self.cached_release();target,_=self.transaction(result=False)
  before=u.read(u.STATE)
  with patch.object(u,'validate_app',return_value='0.6.7'):u.finish(target)
  self.assertEqual(u.read(u.STATE),before);self.assertEqual((u.HOME/item['name']).read_bytes(),payload)
 def test_completed_install_consumed_once_and_cleans_only_matching_archive(self):
  u=self.u;_,item,_=self.cached_release('v0.6.8');target,j=self.transaction(identified=True)
  j['release']=item;u.write(u.HOME/'transaction.json',j)
  with patch.object(u,'validate_app',return_value='0.6.8'):u.finish(target)
  self.assertEqual(u.read(u.STATE)['phase'],'current');self.assertFalse((u.HOME/item['name']).exists())
  self.cached_release('v0.6.9');before=u.read(u.STATE);u.finish(target)
  self.assertEqual(u.read(u.STATE),before);self.assertTrue((u.HOME/item['name']).exists())
 def test_installed_version_never_moves_back_to_stale_journal_version(self):
  u=self.u;target,_=self.transaction()
  with patch.object(u,'validate_app',return_value='0.6.10'):u.finish(target)
  self.assertEqual(u.read(u.STATE)['current'],'0.6.10')
 def test_failed_install_keeps_verified_download_ready_for_retry(self):
  u=self.u;_,item,payload=self.cached_release('v0.6.8');target,j=self.transaction(result=False,identified=True)
  j['release']=item;u.write(u.HOME/'transaction.json',j);u.state(phase='prepared',transaction_id=j['id'])
  with patch.object(u,'validate_app',return_value='0.6.7'):u.finish(target)
  state=u.read(u.STATE)
  self.assertEqual(state['phase'],'ready');self.assertEqual(state['current'],'0.6.7');self.assertTrue(state['error'])
  self.assertEqual((u.HOME/item['name']).read_bytes(),payload);self.assertFalse((u.HOME/'transaction.json').exists())
 def test_failed_install_does_not_offer_corrupt_archive(self):
  u=self.u;_,item,_=self.cached_release('v0.6.8');target,_=self.transaction(result=False)
  (u.HOME/item['name']).write_bytes(b'bad')
  with patch.object(u,'validate_app',return_value='0.6.7'):u.finish(target)
  self.assertEqual(u.read(u.STATE)['phase'],'error')
 def test_pending_helper_and_mismatched_result_are_not_consumed(self):
  u=self.u;self.cached_release();target,j=self.transaction(identified=True);before=u.read(u.STATE)
  for result in ({},{'ok':True,'id':'d'*32},{'ok':True}):
   u.write(u.HOME/'install-result.json',result)
   with patch.object(u,'validate_app',side_effect=AssertionError('No matching completed transaction')):u.finish(target)
   self.assertEqual(u.read(u.STATE),before);self.assertTrue((u.HOME/'transaction.json').exists());self.assertTrue(Path(j['stage']).exists())
 def test_failed_result_for_another_app_does_not_change_state(self):
  u=self.u;self.cached_release();target,_=self.transaction(result=False);before=u.read(u.STATE)
  u.finish(target.parent/'another-app');self.assertEqual(u.read(u.STATE),before)
 def test_result_success_with_old_app_keeps_recovery_files(self):
  u=self.u;self.cached_release();target,j=self.transaction()
  with patch.object(u,'validate_app',return_value='0.6.7'):
   with self.assertRaises(ValueError):u.finish(target)
  self.assertTrue(Path(j['stage']).exists());self.assertTrue((u.HOME/'transaction.json').exists())
 def test_check_reuses_verified_package_after_note_edit_or_interrupted_check(self):
  u=self.u;data,item,_=self.cached_release();data['body']='Updated release description'
  u.state(phase='checking')
  with patch.object(u,'fetch_release',return_value=data):result=u.check('0.6.8')
  self.assertEqual(result['phase'],'ready');self.assertEqual(result['release']['notes'],data['body'])
  (u.HOME/item['name']).write_bytes(b'corrupt')
  with patch.object(u,'fetch_release',return_value=data):result=u.check('0.6.8')
  self.assertEqual(result['phase'],'available')
 def test_completed_download_without_journal_survives_offline_restart(self):
  u=self.u;_,item,payload=self.cached_release();before=u.read(u.STATE)
  u.write(u.HOME/'install-result.json',{'ok':True}) # Orphaned legacy result is inert.
  with patch.object(u,'fetch_release',side_effect=AssertionError('Offline')),patch.object(u,'validate_app',side_effect=AssertionError('No transaction')):
   u.finish(Path(self.tmp.name)/'app')
  self.assertEqual(u.read(u.STATE),before);self.assertEqual((u.HOME/item['name']).read_bytes(),payload)
 def test_offline_automatic_check_after_restart_keeps_completed_download(self):
  u=self.u;_,item,payload=self.cached_release();u.state(checked_at=0)
  u.finish(Path(self.tmp.name)/'app')
  with patch.object(u,'fetch_release',side_effect=OSError('Network unavailable')),patch.object(u,'download',side_effect=AssertionError('Must not re-download')),patch.object(sys,'argv',['updater','check','--current','0.6.8','--automatic']):
   self.assertEqual(u.main(),0)
  result=u.read(u.STATE)
  self.assertEqual(result['phase'],'ready');self.assertEqual(result['release'],item);self.assertEqual(result['error'],'Network unavailable')
  self.assertEqual((u.HOME/item['name']).read_bytes(),payload)
 def test_backend_updaters_are_identical(self):
  source=Path(__file__).resolve().parents[1]
  self.assertEqual((source/'src/updater.py').read_bytes(),(source/'windows/backend/updater.py').read_bytes())

if __name__=='__main__':unittest.main()
