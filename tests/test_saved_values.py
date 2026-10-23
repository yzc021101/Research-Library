"""Real OOXML cache semantics, display formats, and search context regression."""
import os, sys, tempfile, unittest, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from openpyxl import Workbook
fixture=tempfile.TemporaryDirectory();os.environ['RESEARCH_LIBRARY_ROOT']=fixture.name
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from document_formats import spreadsheet_units
from excel_values import display_value

class SavedValues(unittest.TestCase):
    def test_formats(self):
        for raw,fmt,expected in [(0.25,'0.0%','25.0%'), (1234.5,'#,##0.00','1,234.50'),
            (-12.3,'#,##0.0;(#,##0.0)','(12.3)'),(1234000,'0.0,," million"','1.2 million'),
            (0,'0.0;[Red](0.0);"-"','-'),(120,'0.##','120'),(12,'"¥"#,##0.00','¥12.00'),
            (1.25,'[>=1]0.0;0.00','1.25')]:
            with self.subTest(fmt=fmt):self.assertEqual(display_value(raw,fmt),expected)
    def test_saved_results_in_first_row_and_blank_vs_missing(self):
        p=Path(fixture.name)/'model.xlsx';w=Workbook();s=w.active
        for col in 'ABCDE':s[col+'1']='=1+2'
        s['A1'].number_format='0.0%';s['E1'].number_format='#,##0.00';w.save(p)
        ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        with zipfile.ZipFile(p) as z:entries={i.filename:z.read(i) for i in z.infolist()}
        root=ET.fromstring(entries['xl/worksheets/sheet1.xml'])
        for c in root.iter(ns+'c'):
            v=c.find(ns+'v');key=c.get('r')
            if key=='A1':v.text='0.25'
            elif key=='B1':c.set('t','str');v.text=''
            elif key=='D1':c.set('t','e');v.text='#REF!'
            elif key=='E1':v.text='1234.5'
        entries['xl/worksheets/sheet1.xml']=ET.tostring(root)
        with zipfile.ZipFile(p,'w') as z:
            for name,data in entries.items():z.writestr(name,data)
        units,_,warnings=spreadsheet_units(p)
        try:
            text=units[0].text;cells=units[0].tables[0]['rows'][0]['cells']
            self.assertNotIn('=1+2',text)
            self.assertIn('A1=25.0%',text);self.assertIn('E1=1,234.50',text)
            self.assertEqual(cells['B']['text'],'');self.assertTrue(cells['B']['cached_result'])
            self.assertFalse(cells['C']['cached_result']);self.assertIn('缺少',cells['C']['text'])
            self.assertEqual(cells['D']['text'],'#REF!')
            self.assertEqual(cells['A']['saved_value'],.25)
            self.assertTrue(any('1 个单元格缺少' in w for w in warnings))
            self.assertTrue(any('1 个单元格公式结果' in w for w in warnings))
        finally:units.close()

if __name__=='__main__':unittest.main()
