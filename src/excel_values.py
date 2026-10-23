"""Display saved spreadsheet values; never evaluate formulas or external links."""
import re
from datetime import datetime, date, time


def display_value(value, number_format='General'):
    if value is None: return ''
    if isinstance(value, bool): return 'TRUE' if value else 'FALSE'
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time() and not re.search('[hs]', number_format.lower()) else value.isoformat(sep=' ')
    if isinstance(value, (date, time)): return value.isoformat()
    if not isinstance(value, (int, float)): return str(value)
    # Common model formats. Unknown/custom conditional formats retain the exact
    # saved value instead of guessing a currency, scale, sign or unit.
    sections = re.split(r';(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', number_format)
    index = 2 if value == 0 and len(sections) > 2 else 1 if value < 0 and len(sections) > 1 else 0
    fmt = sections[index]
    fmt = re.sub(r'\[(?:Black|Blue|Cyan|Green|Magenta|Red|White|Yellow|Color\d+)\]', '', fmt, flags=re.I)
    fmt = re.sub(r'_.|\*.', '', fmt)
    fmt = re.sub(r'\[\$([^\]-]*)-[^\]]+\]', lambda m: '"'+m[1]+'"', fmt)
    if '[' in fmt or '?' in fmt or re.search(r'[Ee][+-]?0|/', fmt): return str(value)
    literals = []
    def literal(m):
        literals.append(m[1] if m[1] is not None else m[2]); return chr(0xE000+len(literals)-1)
    fmt = re.sub(r'"([^"]*)"|\\(.)', literal, fmt)
    match = re.search(r'[0#][0#,]*(?:\.[0#]+)?', fmt)
    def restore(text):
        for i, s in enumerate(literals): text = text.replace(chr(0xE000+i), s)
        return text
    if not match:
        return restore(fmt) if literals and not re.search('[A-Za-z]', fmt) else str(value)
    prefix, suffix = fmt[:match.start()], fmt[match.end():]
    if re.search(r'[A-Za-z0-9#]', prefix+suffix): return str(value)
    pattern = match[0]; trailing_commas = len(pattern)-len(pattern.rstrip(','))
    pattern = pattern.rstrip(',')
    extra_commas = len(suffix)-len(suffix.lstrip(',')); suffix = suffix[extra_commas:]
    scaled = abs(value) if index == 1 else value
    scaled = scaled / (1000 ** (trailing_commas+extra_commas)) * (100 ** (prefix+suffix).count('%'))
    decimals = pattern.split('.')[1] if '.' in pattern else ''
    result = format(scaled, (',' if ',' in pattern else '')+'.'+str(len(decimals))+'f')
    optional = len(decimals)-len(decimals.rstrip('#'))
    for _ in range(optional):
        if result.endswith('0'): result=result[:-1]
    result=result.rstrip('.')
    return restore(prefix+result+suffix)
