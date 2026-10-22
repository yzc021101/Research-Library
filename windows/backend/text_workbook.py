"""Recognize text tables mislabeled XLS; no script, macro, or link execution."""
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
import tempfile
from defusedxml import ElementTree as ET
from paths import ROOT

class HTMLTable(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None;self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.skip+=1
        elif not self.skip:
            if tag=='tr': self.row=[]
            elif tag in ('td','th') and self.row is not None:self.cell=[]
            elif tag=='br' and self.cell is not None:self.cell.append('\n')
    def handle_data(self, text):
        if not self.skip and self.cell is not None:self.cell.append(text)
    def handle_endtag(self, tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
        elif tag in ('td','th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip());self.cell=None
        elif tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None


def detect(path):
    with open(path,'rb') as f: head=f.read(4096)
    # Text-only formats; an OLE compound file stays on the LibreOffice route.
    if head.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):return None
    if head.startswith((b'\xff\xfe',b'\xfe\xff')):text=head.decode('utf-16',errors='ignore').lower()
    else:text=head.decode('utf-8-sig',errors='ignore').lower()
    if 'urn:schemas-microsoft-com:office:spreadsheet' in text:return 'spreadsheetml'
    if '<html' in text or '<table' in text:return 'html'
    return None


@contextmanager
def converted(path, kind):
    from document_formats import decode_text, MAX_BYTES
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    if path.stat().st_size>MAX_BYTES:raise ValueError('文本表格超过 100 MB 读取限制。')
    text,_=decode_text(path.read_bytes());book=Workbook(write_only=True)
    if kind=='html':
        parser=HTMLTable();parser.feed(text);sheets=[('Table',enumerate(parser.rows,1))]
    else:
        ns='{urn:schemas-microsoft-com:office:spreadsheet}'
        doc=ET.fromstring(text)
        def rows(sheet):
            row_index=0
            for row in sheet.iter(ns+'Row'):
                row_index=int(row.get(ns+'Index',row_index+1));values=[]
                for c in row.findall(ns+'Cell'):
                    index=int(c.get(ns+'Index',len(values)+1))
                    if not 1<=index<=16384:raise ValueError('XML 表格列号无效。')
                    values.extend([None]*(index-1-len(values)))
                    data=c.find(ns+'Data');values.append(''.join(data.itertext()) if data is not None else None)
                yield row_index,values
        sheets=[(sheet.get(ns+'Name','Sheet'),rows(sheet)) for sheet in doc.iter(ns+'Worksheet')]
    with tempfile.TemporaryDirectory(prefix='text-table-',dir=ROOT/'tmp') as folder:
        try:
            for name,source_rows in sheets:
                ws=book.create_sheet(name[:31]);last=0
                for index,values in source_rows:
                    if not 1<=index<=1048576:raise ValueError('XML 表格行号无效。')
                    while last+1<index:ws.append([]);last+=1
                    cells=[]
                    for value in values:
                        cell=WriteOnlyCell(ws,value=value);cell.data_type='s';cells.append(cell)
                    ws.append(cells);last=index
            if not book.worksheets:raise ValueError('没有识别到表格。')
            target=Path(folder)/'table.xlsx';book.save(target)
            yield target
        finally:book.close()
