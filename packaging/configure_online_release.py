"""Pin component URLs to exact, locally verified GitHub release assets.
Run for each platform before signing. This prepares files; it never uploads.
"""
import argparse,hashlib,json,re,zipfile
from pathlib import Path
from urllib.parse import quote

def configure(catalog,assets,output,repo,tag):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo): raise ValueError('Invalid owner/repository')
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?',tag): raise ValueError('Use an immutable version tag')
    items=json.loads(catalog.read_text(encoding='utf-8-sig'))
    for item in items:
        filename=item['file']
        if Path(filename).name!=filename or not filename.endswith('.zip'): raise ValueError('Unsafe filename')
        p=assets/filename
        if p.stat().st_size!=item['download_bytes']: raise ValueError(f'{filename}: size mismatch')
        h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        if h.hexdigest().lower()!=item['sha256'].lower():raise ValueError(f'{filename}: hash mismatch')
        with zipfile.ZipFile(p) as z:
            if item['entry'] not in z.namelist():raise ValueError(f'{filename}: entry missing')
        item['url']=f'https://github.com/{repo}/releases/download/{tag}/{quote(filename)}'
        item['homepage']='https://tesseract-ocr.github.io/tessdoc/Installation.html' if item['id']=='ocr' else 'https://www.libreoffice.org/download/download-libreoffice/'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n')
    (output.parent/'distribution.json').write_text(json.dumps({'version':tag,'release_url':f'https://github.com/{repo}/releases/tag/{tag}','requires_complete_folder':True},indent=2)+'\n')
    return items
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('catalog',type=Path);a.add_argument('assets',type=Path);a.add_argument('output',type=Path);a.add_argument('--repo',default='yzc021101/Research-Library');a.add_argument('--tag',default='v0.6.3');v=a.parse_args()
    configure(v.catalog,v.assets,v.output,v.repo,v.tag)
    print('Pinned online manifest prepared; publish matching assets before distributing this build.')
