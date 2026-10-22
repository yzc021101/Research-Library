"""Bound OCR raster sizes before allocation; retain source coordinates per tile."""
import math
import tempfile
from pathlib import Path
import pymupdf
from paths import ROOT
from office_ocr import run_tesseract, cancelled

VERSION = 2
MAX_EDGE = 8000
MAX_PIXELS = 16_000_000
MAX_TILES = 128


def regions(rect):
    # Normal pages use 180 DPI. Very long pages preserve their text size by tiling.
    scale = 180 / 72
    width, height = rect.width * scale, rect.height * scale
    if min(width, height) <= 0: raise ValueError('PDF 页面尺寸无效。')
    if max(width, height) / min(width, height) < 6:
        scale *= min(1, MAX_EDGE / max(width, height), math.sqrt(MAX_PIXELS / (width * height)))
        yield pymupdf.Rect(rect), scale
        return
    # Cap the short side, then split along the long side with a 64px overlap.
    scale *= min(1, 4000 / min(width, height))
    vertical = rect.height >= rect.width
    short = (rect.width if vertical else rect.height) * scale
    length = min(MAX_EDGE, MAX_PIXELS / max(1, short)) / scale
    overlap = min(64 / scale, length / 10)
    low, high = (rect.y0, rect.y1) if vertical else (rect.x0, rect.x1)
    position = low
    while position < high:
        end = min(position + length, high)
        yield (pymupdf.Rect(rect.x0, position, rect.x1, end) if vertical else
               pymupdf.Rect(position, rect.y0, end, rect.y1)), scale
        if end >= high: break
        position = end - overlap


def remove_overlap(previous, current):
    old, new = previous.splitlines(), current.splitlines()
    for n in range(min(12, len(old), len(new)), 0, -1):
        if [s.strip() for s in old[-n:]] == [s.strip() for s in new[:n]]:
            return '\n'.join(new[n:])
    return current


def recognize_page(page, page_no, event=None, progress=None):
    texts, errors, records = [], [], []
    for index, (clip, scale) in enumerate(regions(page.rect), 1):
        cancelled(event)
        if index > MAX_TILES:
            errors.append('本页超过 128 个识别区域，剩余区域未识别。'); break
        if progress: progress(stage='ocr', image=page_no, location=f'PDF 第 {page_no} 页 · 区域 {index}')
        record = {'region': index, 'bbox_points': list(clip), 'status': 'pending'}
        with tempfile.TemporaryDirectory(prefix='pdf-ocr-', dir=ROOT/'tmp') as folder:
            target = Path(folder)/'input.png'
            try:
                # Clip at rendering time: never allocate the original huge bitmap.
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip,
                                        colorspace=pymupdf.csGRAY, alpha=False)
                record['pixels'] = [pixmap.width, pixmap.height]
                pixmap.save(target); del pixmap
                text = run_tesseract(['tesseract', str(target), 'stdout', '-l', 'eng+chi_sim', '--psm', '3'], event, timeout=120).strip()
                if texts: text = remove_overlap(texts[-1], text)
                if text: texts.append(text)
                record['status'] = 'recognized' if text else 'empty'
            except InterruptedError: raise
            except Exception as exc:
                message = f'第 {page_no} 页区域 {index}：{str(exc)[:400]}'
                errors.append(message); record.update(status='failed', error=message)
        records.append(record)
    return '\n\n'.join(texts), errors, records
