"""A presentation-only parser upgrade must reuse unchanged embeddings, but repair missing ones."""
from pathlib import Path
import os, sys, json
import numpy as np
lab=Path(__file__).resolve().parents[1];import tempfile
root=Path(tempfile.mkdtemp(prefix='vector-upgrade-'))
os.environ['RESEARCH_LIBRARY_ROOT']=str(root);sys.path.insert(0,str(lab/'src'))
import library
from library import Library
from paths import INBOX
p=INBOX/'note.txt';p.write_text('TableVectorMigrationAnchor')
lib=Library(lambda:{'source_folders':[str(INBOX)],'search_mode':'keyword','keep_snapshots':False})
lib.sync();doc=next(iter(lib.active_docs()));table=lib.vector_table()
chunks=lib.db.execute('SELECT chunk_id FROM chunks WHERE doc_id=?',(doc,)).fetchall()
table.add([{'chunk_id':r[0],'doc_id':doc,'vector':[.1]*384} for r in chunks])
library.available=lambda _:True
import ingestion
ingestion.available=lambda _:True
class FakeEmbedder:
    calls=0
    def passage_embed(self, texts, batch_size):
        self.calls+=1
        return [np.array([.2]*384) for _ in texts]
fake=FakeEmbedder();lib._embedder=fake
lib.embedder=lambda:fake

def old_version():
    m=json.loads(lib.db.execute('SELECT metadata FROM documents WHERE doc_id=?',(doc,)).fetchone()[0]);m['parser_version']=3
    lib.db.execute('UPDATE documents SET metadata=? WHERE doc_id=?',(json.dumps(m),doc));lib.db.commit()
old_version();lib.sync();assert fake.calls==0
old_version();table.delete(f"doc_id = '{doc}'");lib.sync();assert fake.calls==1 and lib.vector_table().count_rows()==len(chunks)
print(json.dumps({'unchanged_vectors_reused':True,'missing_vectors_rebuilt':True}))
lib.db.close()
