"""Explicit-download worker. Builds a new vector table without changing the active index."""
from paths import ROOT, DATA
from models import spec, create_embedder, mark_downloaded, table_schema
import json
import sqlite3
import sys
import hashlib


def chunk_fingerprint(rows):
    h = hashlib.sha256()
    for row in rows:
        h.update(json.dumps(list(row), ensure_ascii=False).encode())
    return h.hexdigest()


def build(model_id, table_name, job_dir, factory=create_embedder, allow_download=True):
    import lancedb
    job_dir.mkdir(parents=True, exist_ok=True)
    def progress(phase, completed=0, total=0):
        temp = job_dir / "progress.tmp"
        temp.write_text(json.dumps({"phase": phase, "completed": completed, "total": total}))
        temp.replace(job_dir / "progress.json")
    progress("downloading")
    model = factory(model_id, allow_download=allow_download)
    # Warm up and validate dimensions before recording a usable download.
    vector = next(model.query_embed("model readiness check"))
    if len(vector) != spec(model_id)["dimensions"]: raise ValueError("模型维度不匹配")
    mark_downloaded(model_id)
    db = sqlite3.connect(f"file:{DATA / 'library.sqlite3'}?mode=ro", uri=True)
    try: rows = db.execute("SELECT chunk_id,doc_id,text FROM chunks ORDER BY chunk_id").fetchall()
    finally: db.close()
    vectors = lancedb.connect(str(DATA / "vectors"))
    table = vectors.create_table(table_name, schema=table_schema(model_id))
    progress("indexing", 0, len(rows))
    for start in range(0, len(rows), 16):
        batch = rows[start:start+16]
        encoded = list(model.passage_embed([r[2] for r in batch], batch_size=16))
        if len(encoded) != len(batch): raise ValueError("向量数量不匹配")
        table.add([{"chunk_id": r[0], "doc_id": r[1], "vector": v.tolist()} for r, v in zip(batch, encoded)])
        progress("indexing", min(start+len(batch), len(rows)), len(rows))
    if table.count_rows() != len(rows): raise ValueError("索引不完整")
    result = {"model": model_id, "table": table_name, "count": len(rows), "fingerprint": chunk_fingerprint(rows)}
    temp = job_dir / "result.tmp"
    temp.write_text(json.dumps(result)); temp.replace(job_dir / "result.json")
    progress("ready", len(rows), len(rows))
    return result

if __name__ == "__main__":
    import re
    from pathlib import Path
    model_id, table, job, local_only = sys.argv[1:]
    if not re.fullmatch(r"model_[a-f0-9]{32}", table): raise ValueError("Invalid index name")
    job_dir = Path(job).resolve()
    if job_dir.parent != (DATA / "model-jobs").resolve(): raise ValueError("Invalid job directory")
    build(model_id, table, job_dir, allow_download=local_only != "local-only")
