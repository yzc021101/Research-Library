"""Reject ARM executables in an x64 portable release without executing files."""
from pathlib import Path
import collections,json,struct,sys
root=Path(sys.argv[1]); rows=[]
for p in root.rglob('*'):
 if not p.is_file() or p.suffix.lower() not in {'.exe','.dll','.pyd'}:continue
 with p.open('rb') as f:
  if f.read(2)!=b'MZ':continue
  f.seek(60);pos=struct.unpack('<I',f.read(4))[0];f.seek(pos)
  if f.read(4)!=b'PE\0\0':continue
  machine=struct.unpack('<H',f.read(2))[0]
  f.seek(pos+28);code_size=struct.unpack('<I',f.read(4))[0]
 rows.append({'path':p.relative_to(root).as_posix(),'machine':hex(machine),'code_bytes':code_size})
# pip/setuptools ship launcher templates for multiple target architectures; these
# are data used to generate scripts, not dependencies loaded by the converter.
launcher_suffixes = ('/setuptools/cli-arm64.exe', '/setuptools/gui-arm64.exe',
                     '/pip/_vendor/distlib/t64-arm.exe', '/pip/_vendor/distlib/w64-arm.exe')
templates = [r for r in rows if '--allow-launcher-templates' in sys.argv and
             r['path'].startswith('program/python-core-') and r['path'].endswith(launcher_suffixes)]
bad=[r for r in rows if r['machine'] not in {'0x8664','0x14c'} and r not in templates]
report={'machines':dict(collections.Counter(r['machine'] for r in rows)),'incompatible':bad,'inactive_launcher_templates':templates,'files':rows}
Path(sys.argv[2]).write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='files'}));assert rows and not bad
