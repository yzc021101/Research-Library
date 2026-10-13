from pathlib import Path
import sys,zipfile,io
from openpyxl import Workbook
from openpyxl.worksheet.formula import ArrayFormula
lab=Path(__file__).resolve().parents[1];sys.path.insert(0,str(lab/'src'))
from document_formats import spreadsheet_units
p=lab/'results/tables-0.6.2/array-formula.xlsx'
w=Workbook();w.active['A1']='ArrayFormulaProbe';w.active['B1']=ArrayFormula(ref='B1',text='=SUM(1,2)');w.save(p)
raw=p.read_bytes();out=io.BytesIO()
with zipfile.ZipFile(io.BytesIO(raw)) as z,zipfile.ZipFile(out,'w') as target:
 for entry in z.infolist():
  data=z.read(entry)
  if entry.filename=='xl/worksheets/sheet1.xml':data=data.replace(b'</f><v></v>',b'</f><v>3</v>')
  target.writestr(entry,data)
p.write_bytes(out.getvalue())
a,_,_=spreadsheet_units(p);b,_,_=spreadsheet_units(p)
assert a[0].text==b[0].text and 'object at' not in a[0].text
cell=a[0].tables[0]['rows'][0]['cells']['B'];assert cell['formula']=='=SUM(1,2)' and cell['text']=='3',cell
print('Array formula: stable expression, preserved cached result, no Python object representation.')
