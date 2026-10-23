"""Rasterize embedded WMF/EMF using the optional, isolated Office converter."""
import io
import json
import zipfile
import struct
from PIL import Image
from paths import ROOT
from legacy_office import conversion_workspace, run_conversion

NS = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
      'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
      'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
      'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
      'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
      'xmlns:xlink="http://www.w3.org/1999/xlink"')


def inspect_emf(blob):
    """Read bounded EMF records before Pillow (zero frame headers crash Pillow).

    Only known non-painting records and zero-area rectangles qualify as empty.
    Unknown records always go through rendering, never silently disappear.
    """
    if len(blob) < 88 or blob[40:44] != b' EMF': return None
    declared, count = struct.unpack_from('<II', blob, 48)
    if declared != len(blob): raise ValueError('EMF 图片记录长度不完整。')
    offset, records, empty, viewport = 0, 0, True, None
    state_only = {1, 9, 10, 11, 12, 14, 33, 34, 37, 48, 75}
    while offset < len(blob):
        if offset+8 > len(blob): raise ValueError('EMF 图片记录不完整。')
        kind, length = struct.unpack_from('<II', blob, offset)
        if length < 8 or length % 4 or offset+length > len(blob): raise ValueError('EMF 图片记录尺寸无效。')
        if kind == 11 and length >= 16:
            x, y = struct.unpack_from('<ii', blob, offset+8)
            if x > 0 and y > 0: viewport = (x, y)
        if kind == 43 and length == 24:
            x1,y1,x2,y2 = struct.unpack_from('<iiii', blob, offset+8)
            if x1 != x2 or y1 != y2: empty = False
        elif kind not in state_only: empty = False
        offset += length; records += 1
    if kind != 14: raise ValueError('EMF 图片缺少结束标记。')
    # Some Office exporters undercount EMF+ comment records. A stale count is
    # not evidence of missing content: render it, but never classify it empty.
    if records != count: empty = False
    x1,y1,x2,y2 = struct.unpack_from('<iiii', blob, 8)
    size = (x2-x1, y2-y1)
    if min(size) <= 0: size = viewport
    return {'empty': empty, 'size': size}


def rasterize(blob, event=None):
    emf = inspect_emf(blob)
    if emf:
        if not emf['size']: raise ValueError('EMF 未提供有效尺寸；请在 Office 中重新保存图片后重试。')
        w,h = emf['size']
        # Repair only the temporary rendering copy, using source viewport units.
        if min(struct.unpack_from('<iiii', blob, 24)[2:]) <= 0:
            fixed=bytearray(blob)
            struct.pack_into('<iiii', fixed, 8, 0, 0, w, h)
            struct.pack_into('<iiii', fixed, 24, 0, 0, round(w*2540/96), round(h*2540/96))
            blob=bytes(fixed)
    else:
        with Image.open(io.BytesIO(blob)) as header: w,h=header.size
    if w <= 0 or h <= 0:
        raise ValueError('矢量图片尺寸无效。')
    scale = min(4.0, 3000 / max(w, h))
    width, height = max(1, round(w * scale)), max(1, round(h * scale))
    suffix = 'emf' if blob[40:44] == b' EMF' else 'wmf'
    # A page matching the image bounds avoids Draw's default A4 margins.
    page_w, page_h = width / 10, height / 10
    tmp = ROOT / 'tmp'; tmp.mkdir(parents=True, exist_ok=True)
    with conversion_workspace(tmp) as folder:
        source = folder / 'vector.odg'
        with zipfile.ZipFile(source, 'w') as z:
            z.writestr('mimetype', 'application/vnd.oasis.opendocument.graphics')
            z.writestr('META-INF/manifest.xml',
                '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
                '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.graphics"/>'
                '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
                '<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>'
                f'<manifest:file-entry manifest:full-path="Pictures/image.{suffix}" manifest:media-type="image/x-{suffix}"/>'
                '</manifest:manifest>')
            z.writestr('styles.xml', f'<office:document-styles {NS} office:version="1.2">'
                '<office:styles/><office:automatic-styles><style:page-layout style:name="pm">'
                f'<style:page-layout-properties fo:page-width="{page_w}mm" fo:page-height="{page_h}mm" '
                'fo:margin-top="0mm" fo:margin-bottom="0mm" fo:margin-left="0mm" fo:margin-right="0mm" style:print-orientation="portrait"/>'
                '</style:page-layout><style:style style:name="Mdp1" style:family="drawing-page">'
                '<style:drawing-page-properties draw:background-size="border" draw:fill="none"/>'
                '</style:style></office:automatic-styles><office:master-styles>'
                '<style:master-page style:name="Default" style:page-layout-name="pm" draw:style-name="Mdp1"/>'
                '</office:master-styles></office:document-styles>')
            z.writestr('content.xml', f'<office:document-content {NS} office:version="1.2">'
                '<office:body><office:drawing><draw:page draw:name="page1" draw:master-page-name="Default">'
                f'<draw:frame svg:x="0mm" svg:y="0mm" svg:width="{page_w}mm" svg:height="{page_h}mm">'
                f'<draw:image xlink:href="Pictures/image.{suffix}" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/>'
                '</draw:frame></draw:page></office:drawing></office:body></office:document-content>')
            z.writestr(f'Pictures/image.{suffix}', blob)
        params = json.dumps({key: {'type': 'long', 'value': str(value)}
                             for key, value in [('PixelWidth', width), ('PixelHeight', height)]})
        run_conversion(source, folder / 'output', folder / 'profile',
                       'png:draw_png_Export:' + params, event=event, timeout=90)
        output = folder / 'output/vector.png'
        if not output.exists():
            raise ValueError('矢量图片转换未产生预览；请检查 Office 转换组件。')
        with Image.open(output) as result:
            if result.width * result.height > 9_000_000:
                raise ValueError('矢量图片转换结果超过安全尺寸。')
            return result.convert('RGBA').copy(), [w, h]
