from pathlib import Path
import concurrent.futures,hashlib,io,json,re,shutil,subprocess,tarfile
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--tessdata',type=Path,required=True)
args=parser.parse_args()
base=Path(__file__).resolve().parent
lock=json.loads((base/'ocr-msys-lock.json').read_text())
cache=args.output.parent/'msys-cache';cache.mkdir(parents=True,exist_ok=True)
payload=args.output;payload.mkdir(parents=True,exist_ok=True)
rows=[]
def fetch(d):
 name=d['FILENAME'][0];p=cache/name;sha=d['SHA256SUM'][0]
 if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
  subprocess.run(['curl','-fsSL','--retry','2','--max-time','240','https://repo.msys2.org/mingw/mingw64/'+name,'-o',str(p)],check=True)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
 package=d['NAME'][0];count=0
 with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['zstd','-dc',str(p)]))) as t:
  for m in t:
   n=m.name
   target=None
   if n.startswith('mingw64/bin/') and (n.lower().endswith('.dll') or n.endswith('/tesseract.exe')):target=payload/Path(n).name
   elif n.startswith('mingw64/share/licenses/'):target=payload/'licenses'/package/Path(n).relative_to('mingw64/share/licenses')
   elif n in ['.PKGINFO','.BUILDINFO']:target=payload/'provenance'/package/n.lstrip('.')
   if target and m.isfile():
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(t.extractfile(m).read());count+=1
 row={'name':package,'version':d['VERSION'][0],'binary_url':'https://repo.msys2.org/mingw/mingw64/'+name,'binary_sha256':sha,'licenses':d.get('LICENSE',[]),'source_url':'https://repo.msys2.org/mingw/sources/'+d['BASE'][0]+'-'+d['VERSION'][0]+'.src.tar.zst','packaged_files':count}
 print(package,count,flush=True);return row
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,lock.values()))
(payload/'SOURCES.json').write_text(json.dumps(rows,indent=2)+'\n')
(payload/'SOURCES.txt').write_text('Windows x64 OCR component assembled from unmodified MSYS2 package binaries. Only tesseract.exe, runtime DLLs and their notices are shipped. Exact package/source URLs and checksums are listed in SOURCES.json. Build recipes, patches and corresponding source for copyleft dependencies accompany this release in ocr-windows-corresponding-source.zip. Dynamic libraries may be replaced with compatible modified builds. No restrictions are imposed on debugging such modifications.\nTesseract and English/Chinese tessdata are Apache-2.0. Language data origin: https://github.com/tesseract-ocr/tessdata_fast .\n')
# Language data previously downloaded from the official repository; retain exact bytes.

(payload/'tessdata').mkdir(exist_ok=True)
for lang in ['eng','chi_sim']:shutil.copy2(args.tessdata/(lang+'.traineddata'),payload/'tessdata'/(lang+'.traineddata'))
print('OCR binary payload complete',flush=True)
