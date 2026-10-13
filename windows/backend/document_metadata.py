"""Conservative local cover metadata, with field-level evidence and null fallbacks."""
import re
from datetime import date, datetime

SCHEMA_VERSION = 2
GENERIC_TITLE = re.compile(r'^(?:Microsoft\s+)?(?:PowerPoint(?:\s+Presentation|\s*演示文稿)?|演示文稿\d*|Presentation\d*|Untitled|无标题)$', re.I)
BRANDS = {
    '华泰研究': '华泰证券', '长江证券': '长江证券', '东北证券': '东北证券',
    '申万宏源研究': '申万宏源', '申万宏源证券': '申万宏源', '国信证券': '国信证券',
    'Bernstein Research': 'Bernstein', 'BERNSTEIN': 'Bernstein',
}

def cover_title(page):
    lines = []
    for block in page.get_text('dict').get('blocks', []):
        for line in block.get('lines', []):
            spans = [s for s in line['spans'] if s['text'].strip()]
            if not spans: continue
            value = ''.join(s['text'] for s in spans).strip()
            size = max(s['size'] for s in spans)
            if size >= 18 and len(value) >= 4 and not re.search(r'免责声明|证券研究报告|内部参考|团队|研究所|行业研究|投资评级', value):
                lines.append((line['bbox'][1], size, value))
    if not lines: return None
    maximum = max(x[1] for x in lines)
    chosen = sorted((x for x in lines if x[1] >= maximum * .75), key=lambda x:x[0])
    if len(chosen) > 4: return None
    value = ' '.join(x[2] for x in chosen)
    if len(value) > 160 or GENERIC_TITLE.fullmatch(value): return None
    return value

def institution_from_cover(text):
    found = {}
    for line in text.splitlines():
        compact = re.sub(r'\s+', '', line)
        # Only publisher/header lines, not mentions embedded in report prose or sources.
        if re.search(r'资料来源|来源[:：]|引用|转载|摘自', compact): continue
        for marker, name in BRANDS.items():
            normalized = re.sub(r'\s+', '', marker)
            if compact.startswith(normalized) and len(compact) <= 65:
                found[name] = line.strip()
    if len(found) == 1:
        name, evidence = next(iter(found.items()))
        return name, evidence
    return None, None

def cover_date(text):
    full, partial = {}, {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or len(line) > 110: continue
        # Require a publication-like line. A date in body prose is not a report date.
        labelled = re.search(r'报告日期|发布日期|出版日期|日期\s*[:：]|Date\s*:', line, re.I)
        standalone = re.match(r'^(?:报告日期[:：]?|发布日期[:：]?|日期[:：]?)?\s*(?:20\d{2}|\d{1,2}\s+[A-Za-z]+|[A-Za-z]+\s+\d{1,2})',line)
        if not labelled and not standalone and not re.search(r'团队\s+20\d\d',line): continue
        if re.search(r'资料来源|截至|截止|预测|预计|免责|copyright',line,re.I): continue
        match=re.search(r'(?<!\d)(20\d{2})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})\s*日?(?!\d)',line)
        value=None
        if match:
            try: value=date(*map(int,match.groups())).isoformat()
            except ValueError: continue
        else:
            for pattern, fmt in [(r'\b\d{1,2} [A-Za-z]+ 20\d{2}\b','%d %B %Y'),(r'\b[A-Za-z]+ \d{1,2}, 20\d{2}\b','%B %d, %Y')]:
                m=re.search(pattern,line)
                if m:
                    try: value=datetime.strptime(m[0],fmt).date().isoformat()
                    except ValueError: pass
        if value: full[value]=line; continue
        m=re.search(r'(?<!\d)(20\d{2})\s*(?:年|[-/.])\s*(\d{1,2})(?:月)?(?![\d./-])',line)
        if m and 1 <= int(m[2]) <= 12:
            partial[f'{m[1]}-{int(m[2]):02d}']=line
    if len(full)==1:
        value,evidence=next(iter(full.items()));return value,value,'day',evidence
    if not full and len(partial)==1:
        value,evidence=next(iter(partial.items()));return None,value,'month',evidence
    return None,None,None,None

def extract_metadata(path, pdf, cover_text=None):
    embedded=dict(pdf.metadata or {})
    original=(embedded.get('title') or '').strip()
    title=original or path.stem
    fields={'title': {'source':'pdf_metadata' if original else 'filename','evidence':title}}
    if len(pdf) and (not original or GENERIC_TITLE.fullmatch(original)):
        candidate=cover_title(pdf[0])
        if candidate:
            title=candidate; fields['title']={'source':'cover_native_text','pdf_page':1,'evidence':candidate}
    text=cover_text if cover_text is not None else (pdf[0].get_text(sort=True) if len(pdf) else '')
    # Prefer native cover text; OCR is only a fallback for a cover without text.
    native=text.split('[OCR TRANSCRIPTION - CHECK ORIGINAL PAGE]')[0].strip()
    source='cover_native_text' if native else 'cover_ocr'
    evidence_text=native or text.split('[OCR TRANSCRIPTION - CHECK ORIGINAL PAGE]')[-1]
    institution,institution_evidence=institution_from_cover(evidence_text)
    published,display,precision,date_evidence=cover_date(evidence_text)
    if institution: fields['institution']={'source':source,'pdf_page':1,'evidence':institution_evidence}
    if display: fields['published_date']={'source':source,'pdf_page':1,'evidence':date_evidence,'precision':precision}
    return {'title':title,'pdf_title':original or None,'file_name':path.name,
            'author':embedded.get('author') or None,'institution':institution,
            'published_date':published,'publication_date_display':display,'publication_date_precision':precision,
            'source_type':'unclassified','companies':[], 'metadata_schema_version':SCHEMA_VERSION,
            'metadata_provenance':{'fields':fields,'policy':'Local explicit cover evidence only; ambiguous or missing fields null; no creation/modification date used as publication date.'}}
