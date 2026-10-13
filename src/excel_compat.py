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
    with zipfile.ZipFile(path) as original:
        if 'xl/styles.xml' not in original.namelist(): return path, []
        raw = original.read('xl/styles.xml')
        root = ET.fromstring(raw)  # Malformed XML is deliberately not concealed.
        allowed = {
            'vertical': {'top', 'center', 'bottom', 'justify', 'distributed'},
            'horizontal': {'general', 'left', 'center', 'right', 'fill', 'justify', 'centerContinuous', 'distributed'},
        }
        repaired = []
        for alignment in root.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}alignment'):
            for name, values in allowed.items():
                value = alignment.get(name)
                if value is not None and value not in values:
                    repaired.append(f'{name}={value!r}')
                    del alignment.attrib[name]
        if not repaired: return path, []
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as fixed:
            for entry in original.infolist():
                fixed.writestr(entry, ET.tostring(root, encoding='utf-8', xml_declaration=True)
                               if entry.filename == 'xl/styles.xml' else original.read(entry))
        warning = '已兼容读取不规范的 Excel 对齐样式（' + '、'.join(dict.fromkeys(repaired)) + '）；仅在内存中忽略无效对齐值，原文件、单元格值及数字格式未修改。'
        return buffer.getvalue(), [warning]


def open_compatible_books(path):
    from openpyxl import load_workbook
    source, warnings = compatible_workbook(path)
    def load(cached):
        return load_workbook(io.BytesIO(source) if isinstance(source, bytes) else source,
                             read_only=True, data_only=cached, keep_links=False)
    formulas = load(False)
    try:
        return formulas, load(True), warnings
    except Exception:
        formulas.close()
        raise
