"""Lossless cell boundaries for presentation; searchable text remains available.

Offsets refer to the unit's extracted text, never to the original file bytes.
Only source-provided grids are represented; no table is guessed from prose.
"""
from copy import deepcopy


def cell(value, **extra):
    text = '' if value is None else str(value)
    # A malformed or unusually large cell must not create an unbounded UI payload.
    return {'text': text[:4000], **({'truncated': True} if len(text) > 4000 else {}), **extra}


def table(title, rows, columns=None, context=''):
    keys = list(dict.fromkeys(k for row in rows for k in row['cells']))
    return {'title': title, 'columns': columns or [{'key': k, 'label': k} for k in keys],
            'rows': rows, 'context': context}


def slice_tables(tables, start, end):
    result = []
    for source in tables:
        rows = []
        for row in source['rows']:
            if row['_start'] < end and row['_end'] > start:
                value = deepcopy(row)
                value['_start'] = max(row['_start'], start) - start
                value['_end'] = min(row['_end'], end) - start
                rows.append(value)
        if rows:
            result.append({**source, 'rows': rows})
    return result


def display_content(text, tables, start=0, end=None):
    end = len(text) if end is None else end
    selected = slice_tables(tables, start, end)
    visible = text[start:end]
    spans = sorted((r['_start'], r['_end']) for t in selected for r in t['rows'])
    parts, position = [], 0
    for a, b in spans:
        if a > position: parts.append(visible[position:a])
        position = max(position, b)
    parts.append(visible[position:])
    return {'tables': selected, 'display_text': '\n'.join(p.strip() for p in parts if p.strip())}
