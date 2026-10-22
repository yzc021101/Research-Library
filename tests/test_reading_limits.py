"""Cross-platform regressions for sparse Excel, signature routing and bounded OCR."""
import os, sys, tempfile, unittest, zipfile, io
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
os.environ.setdefault('RESEARCH_LIBRARY_ROOT',str(root/'tmp/reading-tests'))
from openpyxl import Workbook
from openpyxl.worksheet.formula import ArrayFormula
from document_formats import extract_document, spreadsheet_units
from paths import ROOT
from pdf_ocr import regions, recognize_page, remove_overlap
from spooled import Spool
import pymupdf

class ReadingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.folder=Path(self.temp.name)
 def tearDown(self): self.temp.cleanup()
 def book(self):
  p=self.folder/'book.xlsx';b=Workbook();s=b.active;s.title='模型'
  s['A1']='Revenue';s['B2']=ArrayFormula(ref='B2',text='=SUM(1,2)');s['C2']=datetime(2026,1,2);s['C2'].number_format='yyyy-mm-dd'
  s['XFD1048576']='SparseEnd';b.save(p)
  out=io.BytesIO()
  with zipfile.ZipFile(p) as z,zipfile.ZipFile(out,'w') as target:
   for entry in z.infolist():
    raw=z.read(entry)
    if entry.filename=='xl/worksheets/sheet1.xml':raw=raw.replace(b'</f><v></v>',b'</f><v>3</v>')
    target.writestr(entry,raw)
  p.write_bytes(out.getvalue());return p
 def test_sparse_coordinates_cache_dates_and_signature(self):
  p=self.book();raw=p.read_bytes();u,_,warnings=spreadsheet_units(p)
  texts='\n'.join(x.text for x in u)
  self.assertIn('SparseEnd',texts);self.assertIn('B2=3',texts);self.assertIn('2026-01-02',texts)
  cells=[r['cells'] for x in u for t in x.tables for r in t['rows']]
  self.assertTrue(any(v.get('B',{}).get('formula')=='=SUM(1,2)' for v in cells))
  u.close();fake=p.with_suffix('.xls');fake.write_bytes(raw)
  meta,units=extract_document(fake);self.assertEqual(meta['detected_format'],'xlsx');self.assertFalse(meta['partial'])
  self.assertIn('SparseEnd','\n'.join(x.text for x in units));units.close();self.assertEqual(p.read_bytes(),raw)
 def test_limit_is_partial_and_large_mode_recovers(self):
  p=self.book()
  with patch('document_formats.MAX_CELLS',2):
   m,u=extract_document(p);self.assertTrue(m['partial']);self.assertIn('Revenue',u[0].text);u.close()
   m,u=extract_document(p,options={'large_file_mode':True});self.assertFalse(m['partial']);self.assertIn('SparseEnd','\n'.join(x.text for x in u));u.close()
 def test_small_declared_dimensions_do_not_hide_values(self):
  p=self.book();out=io.BytesIO()
  with zipfile.ZipFile(p) as z,zipfile.ZipFile(out,'w') as target:
   for info in z.infolist():
    data=z.read(info).replace(b'ref="A1:XFD1048576"',b'ref="A1:A1"') if info.filename=='xl/worksheets/sheet1.xml' else z.read(info)
    target.writestr(info,data)
  p.write_bytes(out.getvalue());u,_,_=spreadsheet_units(p)
  self.assertIn('SparseEnd','\n'.join(x.text for x in u));u.close()
 def test_invalid_print_titles_preserves_content_and_original(self):
  p=self.book();out=io.BytesIO()
  with zipfile.ZipFile(p) as z,zipfile.ZipFile(out,'w') as target:
   for info in z.infolist():
    data=z.read(info)
    if info.filename=='xl/workbook.xml':
     data=data.replace(b'<definedNames/>',b'<definedNames><definedName name="_xlnm.Print_Titles" localSheetId="0">#REF!</definedName></definedNames>')
    target.writestr(info,data)
  raw=out.getvalue();self.assertIn(b'#REF!',zipfile.ZipFile(io.BytesIO(raw)).read('xl/workbook.xml'))
  p.write_bytes(raw);units,_,warnings=spreadsheet_units(p)
  text=' '.join(x.text for x in units);units.close()
  self.assertIn('SparseEnd',text);self.assertIn('B2=3',text);self.assertTrue(warnings)
  self.assertEqual(p.read_bytes(),raw)
 def test_spool_nested_reads(self):
  s=Spool(range(20));self.assertEqual([v for v in s if s[0]==0],list(range(20)));self.assertEqual(s[3:5],[3,4]);s.close()
 def test_ocr_regions_cover_long_page_and_bound_pixels(self):
  rect=pymupdf.Rect(0,0,533/2.5,61383/2.5);tiles=list(regions(rect))
  self.assertGreater(len(tiles),1);self.assertEqual(tiles[0][0].y0,0);self.assertEqual(tiles[-1][0].y1,rect.y1)
  for (clip,scale) in tiles:
   self.assertLessEqual(max(clip.width,clip.height)*scale,8001)
  for a,b in zip(tiles,tiles[1:]):self.assertLess(b[0].y0,a[0].y1)
  clip,scale=next(regions(pymupdf.Rect(0,0,20000,20000)))
  self.assertLessEqual(clip.width*clip.height*scale**2,16_000_001)
 def test_ocr_failure_preserves_other_regions(self):
  doc=pymupdf.open();page=doc.new_page(width=100,height=7000)
  with patch('pdf_ocr.run_tesseract',side_effect=['Alpha\nShared',RuntimeError('bad tile'),'Omega']):
   text,errors,records=recognize_page(page,1)
  self.assertIn('Alpha',text);self.assertIn('Omega',text);self.assertEqual(len(errors),1)
  self.assertEqual(records[1]['status'],'failed');doc.close()
 def test_html_and_xml_mislabeled_xls(self):
  for kind,content in [('html','<html><table><tr><td>Revenue</td><td>123</td></tr></table><script>Forbidden()</script></html>'),('spreadsheetml','<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet><Table><Row><Cell><Data>Revenue</Data></Cell><Cell><Data>123</Data></Cell></Row></Table></Worksheet></Workbook>')]:
   p=self.folder/(kind+'.xls');p.write_text(content)
   m,u=extract_document(p);self.assertEqual(m['detected_format'],kind)
   text=' '.join(x.text for x in u);self.assertIn('123',text);self.assertNotIn('Forbidden',text);u.close()
 def test_overlap(self):self.assertEqual(remove_overlap('Alpha\nBeta','Beta\nGamma'),'Gamma')

if __name__=='__main__':unittest.main()
