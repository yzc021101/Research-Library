"""Pack only a component payload; preserve internal macOS framework symlinks."""
from pathlib import Path
import hashlib, json, os, stat, sys, zipfile
source, archive, component, entry = map(str,sys.argv[1:])
source=Path(source);archive=Path(archive);archive.parent.mkdir(parents=True,exist_ok=True)
size=0
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for parent,dirs,files in os.walk(source,followlinks=False):
  for name in dirs+files:
   p=Path(parent)/name;rel=p.relative_to(source).as_posix()
   if source.suffix=='.app':rel=source.name+'/'+rel
   if p.is_symlink():
    if not p.resolve().is_relative_to(source.resolve()): raise ValueError('external link: '+str(p))
    info=zipfile.ZipInfo(rel);info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;data=os.readlink(p).encode();z.writestr(info,data);size+=len(data)
   elif p.is_file():
    # Administrative MSI remnants, examples and uninstaller are not runtime inputs.
    if component=='legacy-office' and p.suffix.lower()=='.msi':continue
    if component=='ocr' and ('uninstall' in p.name.lower() or p.suffix.lower() in ('.pdb','.lib')):continue
    z.write(p,rel);size+=p.stat().st_size
item={'id':component,'name':'旧版 Office 转换' if component=='legacy-office' else '图片文字识别（OCR）','description':'本地转换 DOC、PPT、XLS；原文件只读。' if component=='legacy-office' else '扫描 PDF 与 Office 内嵌图片识别，中英文。','entry':entry,'download_bytes':archive.stat().st_size,'expanded_bytes':size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'file':archive.name}
archive.with_suffix('.json').write_text(json.dumps(item,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(item,ensure_ascii=False))
