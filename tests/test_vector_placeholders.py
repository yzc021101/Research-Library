import os,sys,tempfile,struct,unittest
from pathlib import Path
fixture=tempfile.TemporaryDirectory();os.environ['RESEARCH_LIBRARY_ROOT']=fixture.name
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from office_vector import inspect_emf
from office_ocr import recognize,Picture

def emf(records):
    header=bytearray(88);struct.pack_into('<II',header,0,1,88);header[40:44]=b' EMF'
    end=struct.pack('<IIIII',14,20,0,16,20)
    body=b''.join(struct.pack('<II',kind,8+len(data))+data for kind,data in records)+end
    struct.pack_into('<II',header,48,len(header)+len(body),len(records)+2)
    return bytes(header)+body

class PlaceholderTests(unittest.TestCase):
    def test_header_only_empty_without_tesseract(self):
        p=Picture(emf([]),'ppt/media/blank.emf',{})
        self.assertEqual(recognize(p)['skip_reason'],'empty_vector_placeholder')
    def test_zero_rectangle_empty_but_nonzero_kept(self):
        self.assertTrue(inspect_emf(emf([(43,struct.pack('<iiii',0,0,0,0))]))['empty'])
        self.assertFalse(inspect_emf(emf([(43,struct.pack('<iiii',0,0,100,50))]))['empty'])
    def test_unknown_record_never_discarded(self):
        self.assertFalse(inspect_emf(emf([(84,b'')]))['empty'])
    def test_corrupt_length_not_ignored(self):
        with self.assertRaises(ValueError):inspect_emf(emf([])[:-1])
    def test_source_viewport_recovers_size(self):
        self.assertEqual(inspect_emf(emf([(11,struct.pack('<ii',1920,1080))]))['size'],(1920,1080))
    def test_stale_count_does_not_reject_real_emf_plus(self):
        data=bytearray(emf([(70,b'EMF+')]));struct.pack_into('<I',data,52,2)
        self.assertFalse(inspect_emf(bytes(data))['empty'])

if __name__=='__main__':unittest.main()
