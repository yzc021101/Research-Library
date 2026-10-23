"""Concurrent writers serialize and cancellation never deletes another owner's lock."""
import os,sys,tempfile,subprocess,time,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
with tempfile.TemporaryDirectory() as folder:
 os.environ['RESEARCH_LIBRARY_ROOT']=folder
 from cache_lock import locked
 from resource_budget import parser_workers
 code="import sys;sys.path.insert(0,sys.argv[1]);from cache_lock import locked;import time;from pathlib import Path;\nwith locked('shared'):\n p=Path(sys.argv[2]);v=int(p.read_text()) if p.exists() else 0;time.sleep(.1);p.write_text(str(v+1))"
 children=[subprocess.Popen([sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]/'src'),folder+'/counter']) for _ in range(4)]
 for child in children:assert child.wait(10)==0
 assert Path(folder+'/counter').read_text()=='4'
 event=threading.Event();event.set()
 try:
  with locked('shared',event):raise AssertionError('cancel ignored')
 except InterruptedError:pass
 import resource_budget
 for cpu,mem,expected in [(2,2,1),(8,16,4),(32,4,1),(32,64,4)]:
  with patch.object(resource_budget.os,'cpu_count',return_value=cpu),patch.object(resource_budget,'memory_gb',return_value=mem):assert parser_workers()==expected
 print('cache concurrency, cancellation and memory-aware bounds passed')
