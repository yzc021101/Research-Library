"""Private, bounded-memory scratch sequences; never deserialize external files."""
import pickle
import tempfile
from collections.abc import Sequence
from paths import ROOT

class Spool(Sequence):
    def __init__(self, values=()):
        self.file = tempfile.TemporaryFile(dir=ROOT/'tmp')
        self.offsets = []
        self.extend(values)
    def append(self, value):
        self.file.seek(0, 2)
        self.offsets.append(self.file.tell())
        pickle.dump(value, self.file, protocol=5)
    def extend(self, values):
        for value in values: self.append(value)
    def __len__(self): return len(self.offsets)
    def __getitem__(self, index):
        if isinstance(index, slice): return [self[i] for i in range(*index.indices(len(self)))]
        self.file.seek(self.offsets[index])
        return pickle.load(self.file)
    def __iter__(self):
        for i in range(len(self)): yield self[i]
    def close(self): self.file.close()
    def __del__(self):
        if hasattr(self, 'file'): self.file.close()
