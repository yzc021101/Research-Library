"""Build a relocatable Tesseract component from the already installed macOS tool."""
from pathlib import Path
import subprocess, shutil, zipfile, json, hashlib
root=Path(__file__).resolve().parents[1]
stage=root/'packaging/ocr-mac';(stage/'bin').mkdir(parents=True,exist_ok=True);(stage/'lib').mkdir(exist_ok=True)
licenses=stage/'licenses';licenses.mkdir(exist_ok=True)
queue=[Path('/opt/homebrew/bin/tesseract').resolve()];seen={};edges={}
while queue:
 source=queue.pop(0)
 if source in seen:continue
 target=stage/('bin' if source.name=='tesseract' else 'lib')/source.name
 shutil.copy2(source,target);seen[source]=target
 deps=[]
 for line in subprocess.check_output(['otool','-L',str(source)],text=True).splitlines()[1:]:
  dep=line.strip().split(' (')[0]
  canonical = None
  if dep.startswith('/opt/homebrew/'):canonical=Path(dep).resolve()
  elif dep.startswith('@loader_path/'):canonical=(source.parent/dep[len('@loader_path/'):]).resolve()
  elif dep.startswith('@rpath/'):
   candidate=source.parent/dep[len('@rpath/'):]
   if candidate.exists():canonical=candidate.resolve()
   else:raise ValueError('Unresolved rpath '+dep+' in '+str(source))
  if canonical:
   if not canonical.is_file():raise ValueError('Missing dependency '+str(canonical))
   deps.append((dep,canonical));queue.append(canonical)
 edges[source]=deps
 # Preserve upstream license notices from each installed formula.
 parts=source.parts
 if 'Cellar' in parts:
  i=parts.index('Cellar');formula=Path(*parts[:i+3])
  for p in formula.rglob('*'):
   if p.is_file() and any(p.name.upper().startswith(x) for x in ('LICENSE','COPYING','NOTICE','AUTHORS','COPYRIGHT')):
    dest=licenses/formula.name/formula.parent.name/p.relative_to(formula);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
for source,target in seen.items():
 target.chmod(0o755)
 if target.suffix=='.dylib':subprocess.run(['install_name_tool','-id','@loader_path/'+target.name,str(target)],check=True,capture_output=True)
 for old,dep in edges[source]:
  new=('@loader_path/../lib/' if target.parent.name=='bin' else '@loader_path/')+seen[dep].name
  subprocess.run(['install_name_tool','-change',old,new,str(target)],check=True,capture_output=True)
 subprocess.run(['codesign','--force','--sign','-',str(target)],check=True,capture_output=True)
extra=root/'packaging/ocr-extra-notices'
if extra.exists():shutil.copytree(extra,licenses/'additional',dirs_exist_ok=True)
(stage/'tessdata').mkdir(exist_ok=True)
for name in ('eng','chi_sim'):
 shutil.copy2('/opt/homebrew/share/tessdata/'+name+'.traineddata',stage/'tessdata'/ (name+'.traineddata'))
(stage/'SOURCES.txt').write_text('Tesseract: https://github.com/tesseract-ocr/tesseract (5.5.2)\nLanguage data: https://github.com/tesseract-ocr/tessdata\nDependencies: Homebrew formula source URLs at https://github.com/Homebrew/homebrew-core\nThis component is optional. Local dylib load paths changed for relocation.\n',encoding='utf-8')
release=root/'dist';release.mkdir(exist_ok=True)
archive=release/'ocr-macos-arm64.zip'
files=[p for p in stage.rglob('*') if p.is_file()]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in files:z.write(p,p.relative_to(stage))
item={'id':'ocr','name':'图片文字识别（OCR）','description':'扫描 PDF 与 Office 内嵌图片识别，中英文。','entry':'bin/tesseract','download_bytes':archive.stat().st_size,'expanded_bytes':sum(p.stat().st_size for p in files),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'file':archive.name}
(root/'packaging/ocr-mac.json').write_text(json.dumps(item,ensure_ascii=False,indent=2))
print(json.dumps(item,ensure_ascii=False))
