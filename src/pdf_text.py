"""Exclude explicit usage notices from search text, preserving them as metadata.

No source PDF is edited. Rotation alone never classifies text as a watermark.
"""
import re

VERSION = 1

def is_notice(text):
    compact = re.sub(r'\s+', '', text)
    return bool(re.search(r'仅供.{0,100}(?:使用|参考)|请勿(?:传播|转载)|禁止(?:传播|转载)|不得(?:传播|转载)|仅限.{0,80}使用', compact))

def search_text(page, fallback):
    retained, notices = [], []
    for block in page.get_text('dict').get('blocks', []):
        lines = block.get('lines', [])
        whole = ''.join(s['text'] for line in lines for s in line.get('spans', []))
        # Some watermark glyphs are emitted as one-character lines in one block.
        fragmented = lines and all(len(''.join(s['text'] for s in l.get('spans', [])).strip()) <= 2 for l in lines)
        drop_block = fragmented and is_notice(whole)
        for line in lines:
            value = ''.join(s['text'] for s in line.get('spans', [])).strip()
            if not value: continue
            if drop_block or is_notice(value):
                notices.append(whole if drop_block else value)
            else:
                retained.append((line['bbox'], value))
    if not notices: return fallback, []
    # Rebuild only affected pages. Group nearby baselines and retain column order.
    rows = []
    for box, value in sorted(retained, key=lambda item: (item[0][1], item[0][0])):
        row = next((r for r in reversed(rows[-4:]) if abs(r[0]-box[1]) <= 3), None)
        if row is None:
            row = [box[1], []]; rows.append(row)
        row[1].append((box[0], value))
    text = '\n'.join('   '.join(v for _, v in sorted(row[1])) for row in rows)
    return text, list(dict.fromkeys(notices))
