"""Repair invalid *visual alignment* values in memory, preserving source bytes.

Do not drop styles: number formats carry date/number semantics. Worksheet XML,
formulas, cached values, style indices and every other ZIP entry are untouched.
"""
import io
import zipfile
from xml.etree import ElementTree as ET


def formula_text(value):
    if isinstance(value, str): return value
    # openpyxl represents array/data-table formulas as objects. repr() contains
    # a process-specific memory address and is neither stable nor a formula.
    text = getattr(value, 'text', None)
    if text: return text
    reference = getattr(value, 'ref', '')
    kind = '数组公式' if type(value).__name__ == 'ArrayFormula' else '数据表公式'
    return f'{kind}（范围 {reference}；文件未提供普通公式表达式）'


def compatible_workbook(path):
    from openpyxl.worksheet.print_settings import PrintTitles
    with zipfile.ZipFile(path) as original:
        replacements, warnings = {}, []
        if 'xl/styles.xml' in original.namelist():
            root = ET.fromstring(original.read('xl/styles.xml'))
            allowed = {'vertical': {'top','center','bottom','justify','distributed'},
                       'horizontal': {'general','left','center','right','fill','justify','centerContinuous','distributed'}}
            repaired = []
            for alignment in root.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}alignment'):
                for name, values in allowed.items():
                    value = alignment.get(name)
                    if value is not None and value not in values:
                        repaired.append(f'{name}={value!r}'); del alignment.attrib[name]
            if repaired:
                replacements['xl/styles.xml'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                warnings.append('兼容读取：在内存副本中忽略无效 Excel 对齐样式；原文件、单元格及数字格式未修改。')
        if 'xl/workbook.xml' in original.namelist():
            workbook = ET.fromstring(original.read('xl/workbook.xml'))
            removed = 0
            for parent in workbook.iter():
                for child in list(parent):
                    if child.get('name') == '_xlnm.Print_Titles':
                        try: PrintTitles.from_string(child.text or '')
                        except (ValueError, TypeError): parent.remove(child); removed += 1
            if removed:
                replacements['xl/workbook.xml'] = ET.tostring(workbook, encoding='utf-8', xml_declaration=True)
                warnings.append(f'兼容读取：在内存副本中忽略 {removed} 条无效打印标题定义；不修改原文件、工作表内容或公式。')
        if not replacements: return path, warnings
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as fixed:
            for entry in original.infolist():
                fixed.writestr(entry, replacements.get(entry.filename, original.read(entry)))
        return buffer.getvalue(), warnings


def open_compatible_books(path):
    from openpyxl import load_workbook
    source, warnings = compatible_workbook(path)
    def load(cached):
        stream = io.BytesIO(source) if isinstance(source, bytes) else open(source, 'rb')
        try:
            book = load_workbook(stream, read_only=True, data_only=cached, keep_links=False)
            book._research_stream = stream
            return book
        except BaseException:
            stream.close()
            raise
    formulas = load(False)
    try:
        return formulas, load(True), warnings
    except Exception:
        formulas.close()
        formulas._research_stream.close()
        raise


def sparse_rows(sheet, cancel=None):
    """Use the pinned openpyxl 3.1 parser without expanding absent cells/rows.

    Coordinates, date styles, shared strings and array formulas use openpyxl's
    normal reader. Ignore producer-supplied dimensions, which may be stale.
    """
    from openpyxl.worksheet._reader import WorkSheetParser
    from openpyxl.cell.read_only import ReadOnlyCell
    from office_ocr import cancelled
    with sheet._get_source() as stream:
        parser = WorkSheetParser(stream, sheet._shared_strings,
            data_only=sheet.parent.data_only, epoch=sheet.parent.epoch,
            date_formats=sheet.parent._date_formats,
            timedelta_formats=sheet.parent._timedelta_formats)
        for index, row in parser.parse():
            cancelled(cancel)
            yield index, {c['column']: ReadOnlyCell(sheet, **c) for c in row if c['value'] is not None}
