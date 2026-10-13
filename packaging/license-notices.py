from pathlib import Path
import importlib.metadata as md,json,sys,zipfile
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
rows=[]
for dist in md.distributions():
 name=dist.metadata['Name'] or 'unknown'
 if name.lower() in ('pyinstaller','pyinstaller-hooks-contrib','altgraph','setuptools','macholib','pefile','pywin32-ctypes'):continue
 rows.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License',''),'source':dist.metadata.get('Home-page','')})
 for f in dist.files or []:
  if any(x in str(f).lower() for x in ('license','licence','copying','copyright','notice')):
   source=Path(dist.locate_file(f))
   if source.is_file() and source.stat().st_size<1000000:
    target=out/name/str(f).replace('/','_').replace('\\','_');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
(out/'dependencies.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'README.txt').write_text('Third-party components retain their own licenses.\nPyMuPDF is AGPL-3.0: https://github.com/pymupdf/PyMuPDF\nPublic redistribution requires a separately verified corresponding-source bundle and license compliance review. This generated inventory does not certify release compliance.\nLibreOffice is an optional, unmodified component: https://www.libreoffice.org/about-us/licenses/\nMatching LibreOffice source: https://downloadarchive.documentfoundation.org/libreoffice/old/25.8.6.2/src/\nTesseract source: https://github.com/tesseract-ocr/tesseract\nModel weights are separate optional downloads under their upstream licenses.\n',encoding='utf-8')
