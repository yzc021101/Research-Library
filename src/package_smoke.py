"""Runs only with a deliberately isolated test root; no user data is touched."""
from paths import ROOT, PACKAGED
import json, os
if not os.environ.get('RESEARCH_LIBRARY_ROOT'): raise RuntimeError('Explicit test root required')
from settings import save_settings
save_settings({'source_folders':[str(ROOT/'inbox')], 'app_managed':True})
(ROOT/'inbox/打包测试.txt').write_text('PackagingProbe 超节点互连参数 800 Gbps',encoding='utf-8')
from library import Library
from settings import load_settings
lib=Library(load_settings)
sync=lib.sync()
result=lib.search('PackagingProbe', mode='hybrid')
assert result['count']==1 and result['mode']=='keyword',result
unit=lib.read_unit(result['results'][0]['doc_id'],1)
assert '800 Gbps' in json.dumps(unit,ensure_ascii=False)
# Real native libraries must load inside the packaged runtime.
import pyarrow, lancedb, onnxruntime, tokenizers, pymupdf
from fastembed import TextEmbedding
from docx import Document
from pptx import Presentation
from openpyxl import Workbook
from striprtf.striprtf import rtf_to_text
assert len(TextEmbedding.list_supported_models())>0
print(json.dumps({'ok':True,'frozen':PACKAGED,'root':str(ROOT),'keyword_hits':result['count'],'mode':result['mode'],'native_imports':True},ensure_ascii=False))
