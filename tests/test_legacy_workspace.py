"""Actual long-path cleanup; creates no documents or persistent user settings."""
import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from legacy_office import conversion_workspace
with tempfile.TemporaryDirectory(prefix='rl-cleanup-test-') as parent:
    with conversion_workspace(parent) as workspace:
        deep=workspace / ('a'*70) / ('b'*70) / ('c'*70) / 'fixture.txt'
        target=str(deep.resolve())
        if os.name=='nt':target='\\\\?\\'+target
        os.makedirs(os.path.dirname(target));Path(target).write_text('synthetic fixture')
        assert len(target)>260
    assert not workspace.exists()
print('long-path conversion workspace cleanup passed')
