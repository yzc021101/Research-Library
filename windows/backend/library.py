from paths import ROOT, INBOX, DATA, MODEL, inside
from models import available, spec, create_embedder, table_schema
from document_metadata import extract_metadata, SCHEMA_VERSION
from document_formats import SUPPORTED, LEGACY, PARSER_VERSION, extract_document
from table_content import display_content
import csv
import hashlib
import io
import json
import re
import shutil
import sqlite3
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def tokens(text):
    # ASCII model names/units stay intact; CJK bigrams make Chinese text searchable.
    out = re.findall(r"[a-zA-Z0-9]+(?:[._-][a-zA-Z0-9]+)*", text.lower())
    for s in re.findall(r"[\u3400-\u9fff]+", text):
        out.extend(s[i:i+2] for i in range(max(1, len(s)-1)))
    return list(dict.fromkeys(out))

def search_suggestions(documents):
    """Use active report titles, without model inference or invented topics."""
    suggestions, seen = [], set()
    generic = {"powerpoint 演示文稿", "powerpoint presentation", "microsoft powerpoint", "presentation", "未命名文档", "untitled"}
    for doc in sorted(documents, key=lambda d: (d.get("published_date") or "", d.get("indexed_at") or "", d.get("doc_id") or ""), reverse=True):
        title = re.sub(r"\s+", " ", doc.get("title") or "").strip()
        if not title or title.casefold() in generic or not tokens(title):
            continue
        query = title[:120]
        if query.casefold() not in seen:
            suggestions.append(query)
            seen.add(query.casefold())
        if len(suggestions) == 3:
            break
    return suggestions

def split_text(text, limit=1400):
    # Keep line order, overlap a few lines; read_page supplies the unsplit table.
    lines = text.splitlines(keepends=True)
    start = 0
    while start < len(lines):
        end, size = start, 0
        while end < len(lines) and (size + len(lines[end]) <= limit or end == start):
            size += len(lines[end]); end += 1
        value = "".join(lines[start:end]).strip()
        if value:
            if len(value) <= limit:
                yield value, start + 1, end
            else:
                # A long paragraph/row must not become one silently truncated embedding.
                for offset in range(0, len(value), limit - 120):
                    yield value[offset:offset+limit], start + 1, end
        if end == len(lines):
            break
        start = max(start + 1, end - 3)

from storage import StorageMixin

class Library(StorageMixin):
    def __init__(self, settings_provider=None):
        self.settings_provider = settings_provider
        self.lock = threading.RLock()
        self.progress_lock = threading.Lock()
        self.sync_progress = {'stage': 'idle'}
        self.sync_cancel = threading.Event()
        self.db = sqlite3.connect(DATA / "library.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS library_config(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS documents(
            doc_id TEXT PRIMARY KEY, sha256 TEXT, snapshot TEXT, metadata TEXT,
            page_count INTEGER, indexed_at TEXT);
        CREATE TABLE IF NOT EXISTS sources(
            path TEXT PRIMARY KEY, doc_id TEXT, state TEXT, error TEXT, checked_at TEXT);
        CREATE TABLE IF NOT EXISTS pages(
            doc_id TEXT, pdf_page INTEGER, printed_page TEXT, text TEXT,
            method TEXT, review INTEGER, blocks TEXT,
            PRIMARY KEY(doc_id,pdf_page));
        CREATE TABLE IF NOT EXISTS chunks(
            chunk_id TEXT PRIMARY KEY, doc_id TEXT, pdf_page INTEGER,
            line_start INTEGER, line_end INTEGER, text TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED, body, tokenize='unicode61');
        ''')
        self.db.commit()
        if 'location' not in {r[1] for r in self.db.execute('PRAGMA table_info(pages)')}:
            self.db.execute("ALTER TABLE pages ADD COLUMN location TEXT")
            self.db.commit()
        # Upgrade the v0.1 inbox-relative source keys without duplicating UI rows.
        for source in self.db.execute("SELECT path FROM sources").fetchall():
            if not Path(source[0]).is_absolute():
                absolute = str((INBOX / source[0]).absolute())
                if self.db.execute("SELECT 1 FROM sources WHERE path=?", (absolute,)).fetchone():
                    self.db.execute("DELETE FROM sources WHERE path=?", (source[0],))
                else: self.db.execute("UPDATE sources SET path=? WHERE path=?", (absolute, source[0]))
        self.db.commit()
        self._embedder = None
        self._vectors = None
        stored = self.db.execute("SELECT value FROM library_config WHERE key='embedding'").fetchone()
        self.embedding = json.loads(stored[0]) if stored else {"model": MODEL, "table": "passages"}
        spec(self.embedding["model"])

    def settings(self):
        return self.settings_provider() if self.settings_provider else {"source_folders": [str(INBOX)], "top_k": 8, "search_mode": "hybrid", "scan_interval": 15}

    def roots(self):
        return [Path(p).resolve() for p in self.settings()["source_folders"]]

    def source_root(self, path):
        for root in self.roots():
            if path.absolute().is_relative_to(root):
                return root
        raise ValueError("Path outside configured source folders")

    def files(self, metadata=False):
        files = {}
        for root in self.roots():
            if not root.is_dir(): continue
            for p in root.rglob("*"):
                if not p.is_file(): continue
                if p.name.startswith(('~$', '.')): continue
                if p.suffix.lower() in SUPPORTED | LEGACY or (metadata and p.name.endswith(".metadata.json")):
                    # Never ingest the derived cache/snapshots if the lab itself is selected.
                    if p.resolve().is_relative_to(DATA.resolve()): continue
                    excluded = [ROOT / x for x in ('cache', 'tmp', 'results', 'dist', '.venv', 'windows')]
                    if any(p.resolve().is_relative_to(x) and not root.is_relative_to(x) for x in excluded): continue
                    files[str(p.absolute())] = p
        return [files[k] for k in sorted(files)]

    def semantic_ready(self):
        if not available(self.embedding['model']): return False
        count = self.db.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        if not count: return True
        try: return self.vectors().open_table(self.embedding['table']).count_rows() >= count
        except Exception: return False

    def embedder(self):
        if self._embedder is None:
            self._embedder = create_embedder(self.embedding["model"])
        return self._embedder

    def vectors(self):
        if self._vectors is None:
            import lancedb
            self._vectors = lancedb.connect(str(DATA / "vectors"))
        return self._vectors

    def vector_table(self):
        return self.vectors().create_table(self.embedding["table"], schema=table_schema(self.embedding["model"]), exist_ok=True)

    def activate_model(self, result):
        # Only the final pointer change is committed; failures leave the old model usable.
        from model_worker import chunk_fingerprint
        with self.lock:
            spec(result["model"])
            rows = self.db.execute("SELECT chunk_id,doc_id,text FROM chunks ORDER BY chunk_id").fetchall()
            if chunk_fingerprint(rows) != result["fingerprint"]:
                raise ValueError("资料在重建期间发生变化，请重新切换。")
            table = self.vectors().open_table(result["table"])
            if table.count_rows() != len(rows) or table.schema.field("vector").type.list_size != spec(result["model"])["dimensions"]:
                raise ValueError("新索引验证未通过")
            value = {"model": result["model"], "table": result["table"]}
            self.db.execute("INSERT OR REPLACE INTO library_config VALUES('embedding',?)", (json.dumps(value),))
            self.db.commit()
            self.embedding = value
            self._embedder = None

    def metadata(self, path, pdf, cover_text=None):
        result = extract_metadata(path, pdf, cover_text)
        result['file_format'] = 'pdf'
        return self.metadata_overrides(path, result)

    def metadata_overrides(self, path, result):
        sidecar = path.with_suffix(".metadata.json")
        if sidecar.exists():
            inside(sidecar, self.source_root(path))
            overrides = json.loads(sidecar.read_text())
            for key in ("title", "author", "institution", "published_date", "source_type", "companies", "metadata_provenance"):
                if key in overrides: result[key] = overrides[key]
            if "published_date" in overrides:
                result["publication_date_display"] = overrides["published_date"]
                result["publication_date_precision"] = "day" if overrides["published_date"] else None
        return result

    def ocr(self, page, doc_id, page_no):
        if not shutil.which("tesseract"):
            return "", "ocr_unavailable"
        path = ROOT / "tmp" / f"{doc_id}-{page_no}.png"
        page.get_pixmap(dpi=180).save(path)
        try:
            from office_ocr import run_tesseract
            self.set_progress(stage='ocr', image=page_no, location=f'PDF 第 {page_no} 页')
            text = run_tesseract(["tesseract", str(path), "stdout", "-l", "eng+chi_sim", "--psm", "3"], self.sync_cancel, timeout=120)
            return text.strip(), None
        finally:
            path.unlink(missing_ok=True)

    def set_progress(self, **values):
        with self.progress_lock: self.sync_progress.update(values)

    def progress(self):
        with self.progress_lock: return dict(self.sync_progress)

    def cancel_sync(self):
        self.sync_cancel.set()
        return {'cancelling': True}

    def extract(self, path, doc_id):
        if path.suffix.lower() != '.pdf':
            meta, units = extract_document(path, self.set_progress, self.sync_cancel)
            meta = self.metadata_overrides(path, meta)
            pages, chunks = [], []
            for n, unit in enumerate(units, 1):
                review = unit.location.get('kind') == 'embedded_image'
                method = f'{path.suffix[1:].lower()}_' + ('tesseract' if review else 'structured_text')
                pages.append((doc_id, n, None, unit.text, method,
                    int(review), json.dumps({'tables': unit.tables}, ensure_ascii=False), json.dumps(unit.location, ensure_ascii=False)))
                for j, (part, start, end) in enumerate(split_text(unit.text)):
                    chunks.append((f'{doc_id}:u{n}:c{j+1}', doc_id, n, start, end, part))
            return meta, pages, chunks
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass: raise ValueError("Encrypted PDF requires a password")
            layouts = []
            if shutil.which("pdftotext"):
                res = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                     check=True, capture_output=True, timeout=90)
                layouts = res.stdout.decode("utf-8", errors="replace").split("\f")
            pages, chunks = [], []
            for i, page in enumerate(pdf):
                from office_ocr import cancelled
                cancelled(self.sync_cancel)
                text = layouts[i].strip() if i < len(layouts) else page.get_text(sort=True).strip()
                native = text
                method = "pdftotext_layout" if layouts else "pymupdf_text"
                image_area = max((pymupdf.Rect(im["bbox"]).get_area() for im in page.get_image_info()), default=0)
                review = False
                if len(native) < 100 or image_area > page.rect.get_area() * 0.25:
                    ocr, error = self.ocr(page, doc_id, i+1)
                    review = True
                    if ocr:
                        text += "\n\n[OCR TRANSCRIPTION - CHECK ORIGINAL PAGE]\n" + ocr
                        method += "+tesseract"
                    else: method += "+" + (error or "ocr_empty")
                footer = re.search(r"(?:^|\n)[^\n]*?\s{2,}(\d{1,3})\s*$", native)
                printed = footer[1] if footer else None
                blocks = [{"bbox_points": list(b[:4]), "text": b[4]} for b in page.get_text("blocks") if b[6] == 0]
                pages.append((doc_id, i+1, printed, text, method, int(review), json.dumps(blocks),
                    json.dumps({'kind': 'pdf_page', 'pdf_page': i+1, 'label': f'PDF 第 {i+1} 页'})))
                for j, (part, start, end) in enumerate(split_text(text)):
                    chunks.append((f"{doc_id}:p{i+1}:c{j+1}", doc_id, i+1, start, end, part))
            meta = self.metadata(path, pdf, pages[0][3] if pages else "")
            return meta, pages, chunks

    def sync(self, prepared=False):
        with self.lock:
            if not prepared: self.sync_cancel.clear()
            try:
                return self._sync()
            finally:
                self.set_progress(stage='cancelled' if self.sync_cancel.is_set() else 'idle')

    def _sync(self):
        with self.lock:
            # Retry recoverable stylesheet failures first when upgrading the reader.
            style_failures = {r[0] for r in self.db.execute("SELECT path FROM sources WHERE state='failed' AND error LIKE '%stylesheet%'")}
            files = sorted(self.files(), key=lambda p: str(p.absolute()) not in style_failures)
            seen, results = set(), []
            from office_ocr import cancelled
            for file_index, path in enumerate(files, 1):
                if self.sync_cancel.is_set(): break
                self.set_progress(stage='reading', file=path.name, file_index=file_index, file_total=len(files), image=None, location=None)
                rel = str(path.absolute()); seen.add(rel)
                try:
                    inside(path, self.source_root(path))
                    sha = digest(path)
                    identity = sha if path.suffix.lower() == '.pdf' else hashlib.sha256((sha + path.suffix.lower()).encode()).hexdigest()
                    doc_id = "d_" + identity[:24]
                    exists = self.db.execute("SELECT metadata FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
                    rebuild = bool(exists and path.suffix.lower() != '.pdf' and (json.loads(exists[0]).get('parser_version') != PARSER_VERSION or (json.loads(exists[0]).get('ocr_summary') or {}).get('failed', 0)))
                    if exists and not rebuild and path.suffix.lower() in {'.docx', '.pptx', '.xlsx'} | LEGACY:
                        locations = self.db.execute('SELECT location FROM pages WHERE doc_id=?', (doc_id,)).fetchall()
                        for row in locations:
                            relative = json.loads(row[0] or '{}').get('image_path')
                            if relative and not inside(ROOT / relative, ROOT / 'cache/office-ocr').is_file():
                                rebuild = True
                                break
                    if exists and not rebuild:
                        old_meta = json.loads(exists[0])
                        if path.with_suffix(".metadata.json").exists() or old_meta.get("metadata_schema_version", 0) < SCHEMA_VERSION:
                            cover = self.db.execute("SELECT text FROM pages WHERE doc_id=? AND pdf_page=1", (doc_id,)).fetchone()
                            if path.suffix.lower() == '.pdf':
                                with pymupdf.open(path) as pdf: meta = self.metadata(path, pdf, cover[0] if cover else None)
                            else:
                                meta, _ = extract_document(path, self.set_progress, self.sync_cancel)
                                meta = self.metadata_overrides(path, meta)
                            # Preserve existing manually supplied nonempty fields during an upgrade.
                            if not path.with_suffix(".metadata.json").exists():
                                for key in ("institution", "published_date", "source_type", "companies"):
                                    if old_meta.get(key) and old_meta[key] != "unclassified":
                                        meta[key] = old_meta[key]
                                        meta["metadata_provenance"]["fields"][key] = {"source": "preserved_existing_metadata", "evidence": old_meta[key]}
                                        if key == "published_date":
                                            meta["publication_date_display"] = old_meta[key]
                                            meta["publication_date_precision"] = old_meta.get("publication_date_precision") or "day"
                            self.db.execute("UPDATE documents SET metadata=? WHERE doc_id=?", (json.dumps(meta), doc_id))
                        if self.settings().get('keep_snapshots', False):
                            saved = self.db.execute('SELECT snapshot FROM documents WHERE doc_id=?', (doc_id,)).fetchone()[0]
                            if not saved or not (ROOT/saved).is_file():
                                saved = self.snapshot_file(path, sha)
                                self.db.execute('UPDATE documents SET snapshot=? WHERE doc_id=?', (saved, doc_id))
                        action = "unchanged_or_duplicate"
                    else:
                        meta, pages, chunks = self.extract(path, doc_id)
                        cancelled(self.sync_cancel)
                        reuse_vectors = False
                        if rebuild and available(self.embedding["model"]):
                            previous = [tuple(row) for row in self.db.execute(
                                "SELECT chunk_id,doc_id,pdf_page,line_start,line_end,text FROM chunks WHERE doc_id=?", (doc_id,))]
                            if sorted(previous) == sorted(chunks):
                                ids = self.vector_table().search().where(f"doc_id = '{doc_id}'").select(['chunk_id']).limit(len(chunks)+1).to_list()
                                reuse_vectors = len(ids) == len(chunks) and {x['chunk_id'] for x in ids} == {c[0] for c in chunks}
                        if available(self.embedding["model"]) and not reuse_vectors:
                            self.set_progress(stage='embedding')
                            vectors = list(self.embedder().passage_embed([c[5] for c in chunks], batch_size=16))
                            cancelled(self.sync_cancel)
                            table = self.vector_table()
                            table.delete(f"doc_id = '{doc_id}'")
                            if chunks:
                                table.add([{"chunk_id": c[0], "doc_id": doc_id, "vector": v.tolist()}
                                           for c, v in zip(chunks, vectors)])
                        snapshot = self.snapshot_file(path, sha)
                        if digest(path) != sha:
                            raise RuntimeError("File changed during indexing; retry after copy finishes")
                        if rebuild:
                            self.db.execute('DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_id=?)', (doc_id,))
                            self.db.execute('DELETE FROM chunks WHERE doc_id=?', (doc_id,))
                            self.db.execute('DELETE FROM pages WHERE doc_id=?', (doc_id,))
                            self.db.execute('DELETE FROM documents WHERE doc_id=?', (doc_id,))
                        self.db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?)",
                            (doc_id, sha, snapshot, json.dumps(meta), len(pages), now()))
                        self.db.executemany("INSERT INTO pages VALUES(?,?,?,?,?,?,?,?)", pages)
                        self.db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?)", chunks)
                        self.db.executemany("INSERT INTO chunks_fts VALUES(?,?)", [(c[0], " ".join(tokens(c[5]))) for c in chunks])
                        action = "indexed"
                    self.db.execute("INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?)", (rel, doc_id, "ready", None, now()))
                    self.db.commit()
                    results.append({"file": rel, "doc_id": doc_id, "action": action})
                except InterruptedError:
                    self.db.rollback()
                    break
                except Exception as exc:
                    self.db.rollback()
                    self.db.execute("INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?)", (rel, None, "failed", str(exc), now()))
                    self.db.commit()
                    results.append({"file": rel, "action": "failed", "error": str(exc)})
            for row in self.db.execute("SELECT path FROM sources").fetchall():
                if not self.sync_cancel.is_set() and row[0] not in seen:
                    self.db.execute("UPDATE sources SET state='missing',checked_at=? WHERE path=?", (now(), row[0]))
            self.db.commit()
            return {"results": results, "cancelled": self.sync_cancel.is_set(), "status": self.status()}

    def status(self):
        with self.lock:
            sources = [dict(x) for x in self.db.execute("SELECT * FROM sources ORDER BY path")]
            docs = self.active_docs()
            return {"software_license": "AGPL-3.0-only", "source_code_url": "https://github.com/yzc021101/Research-Library/tree/v0.6.7", "root": str(ROOT), "inbox": str(INBOX), "active_documents": len(docs),
                    "supported_formats": sorted(SUPPORTED),
                    "search_suggestions": search_suggestions(docs.values()),
                    "stored_versions": self.db.execute("SELECT count(*) FROM documents").fetchone()[0],
                    "chunk_count": self.db.execute("SELECT count(*) FROM chunks").fetchone()[0],
                    "sources": sources, "embedding_model": self.embedding["model"], "network_during_search": False,
                    "source_folders": [{"path": str(p), "available": p.is_dir()} for p in self.roots()],
                    "watch_mode": "startup sync + configurable polling while service runs"}

    def active_docs(self, institution=None, source_type=None, date_from=None, date_to=None, company=None, doc_id=None):
        allowed = set()
        source_paths = {}
        roots = self.roots()
        for source in self.db.execute("SELECT path,doc_id FROM sources WHERE state='ready'"):
            path = Path(source[0])
            if not path.is_absolute(): path = INBOX / path
            if any(path.resolve().is_relative_to(root) for root in roots):
                allowed.add(source[1])
                source_paths.setdefault(source[1], []).append(path)
        rows = self.db.execute("SELECT * FROM documents").fetchall()
        out = {}
        for row in rows:
            if row["doc_id"] not in allowed: continue
            d = dict(row); m = json.loads(d.pop("metadata")); d.update(m)
            if doc_id and d["doc_id"] != doc_id: continue
            if institution and institution.lower() not in (d.get("institution") or "").lower(): continue
            if source_type and source_type != d.get("source_type"): continue
            if company and company.lower() not in json.dumps(d.get("companies", []), ensure_ascii=False).lower(): continue
            date = d.get("published_date")
            if date_from and (not date or date < date_from): continue
            if date_to and (not date or date > date_to): continue
            d.update(self.citation_info(row, source_paths.get(row['doc_id'], [])))
            d.pop('snapshot', None)
            d.setdefault('file_format', 'pdf')
            d['unit_count'] = d['page_count']
            if d['file_format'] != 'pdf': d['page_count'] = None
            out[d["doc_id"]] = d
        return out

    def search_documents(self, query="", **filters):
        with self.lock:
            docs = list(self.active_docs(**filters).values())
            if query:
                wanted = tokens(query)
                docs = [d for d in docs if any(t in json.dumps(d, ensure_ascii=False).lower() for t in wanted)]
            return {"documents": docs, "count": len(docs)}

    def search(self, query, top_k=None, mode=None, **filters):
        top_k = self.settings()["top_k"] if top_k is None else top_k
        mode = self.settings()["search_mode"] if mode is None else mode
        if not query.strip(): raise ValueError("query cannot be empty")
        if len(query) > 2000: raise ValueError("query must be at most 2000 characters")
        if not 1 <= top_k <= 20: raise ValueError("top_k must be 1..20")
        if mode not in {"hybrid", "keyword", "semantic"}: raise ValueError("Unknown retrieval mode")
        requested_mode = mode
        if mode != 'keyword' and not self.semantic_ready():
            if mode == 'semantic': raise ValueError('请先在设置中下载模型并完成索引重建；也可使用关键词检索。')
            mode = 'keyword'
        with self.lock:
            docs = self.active_docs(**filters)
            if not docs: return {"query": query, "results": [], "count": 0}
            # Values are content-derived IDs, never raw SQL from user text.
            ids_sql = ",".join("'" + k + "'" for k in docs)
            candidates, lex, sem = {}, [], []
            terms = tokens(query)
            if mode != "semantic" and terms:
                expression = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms[:64])
                lex = self.db.execute(f'''SELECT c.*, bm25(chunks_fts) AS lexical_score
                    FROM chunks_fts JOIN chunks c ON c.chunk_id=chunks_fts.chunk_id
                    WHERE chunks_fts MATCH ? AND c.doc_id IN ({ids_sql})
                    ORDER BY lexical_score LIMIT 60''', (expression,)).fetchall()
            if mode != "keyword":
                q = next(self.embedder().query_embed(query)).tolist()
                sem = self.vector_table().search(q).distance_type("cosine").where(f"doc_id IN ({ids_sql})").limit(60).to_list()
            for rank, row in enumerate(lex, 1):
                candidates[row["chunk_id"]] = {"rrf": 1/(60+rank), "keyword_rank": rank}
            for rank, row in enumerate(sem, 1):
                c = candidates.setdefault(row["chunk_id"], {"rrf": 0})
                c.update({"semantic_rank": rank, "cosine_distance": row["_distance"]})
                c["rrf"] += 1/(60+rank)
            output = []
            for cid, ranking in sorted(candidates.items(), key=lambda pair: -pair[1]["rrf"])[:top_k]:
                row = self.db.execute("SELECT * FROM chunks WHERE chunk_id=?", (cid,)).fetchone()
                if row is None: continue
                r = dict(row)
                p = self.db.execute("SELECT printed_page,method,review,location,blocks,text FROM pages WHERE doc_id=? AND pdf_page=?", (r["doc_id"],r["pdf_page"])).fetchone()
                d = docs[r["doc_id"]]
                stored = json.loads(p['blocks'] or '[]')
                grids = stored.get('tables', []) if isinstance(stored, dict) else []
                lines = p['text'].splitlines(keepends=True)
                begin = sum(len(line) for line in lines[:r['line_start']-1])
                finish = sum(len(line) for line in lines[:r['line_end']])
                rendered = display_content(p['text'], grids, begin, finish)
                if not rendered['tables']: rendered['display_text'] = r['text']
                location = json.loads(p[3]) if p[3] else {'kind': 'pdf_page', 'pdf_page': r['pdf_page'], 'label': f"PDF 第 {r['pdf_page']} 页"}
                r['unit_index'] = r['pdf_page']
                if d['file_format'] != 'pdf': r['pdf_page'] = None
                if location['kind'] == 'lines' and 'part' not in location:
                    location = {**location, 'line_start': location['line_start'] + r['line_start'] - 1,
                        'line_end': location['line_start'] + r['line_end'] - 1}
                    location['label'] = f"第 {location['line_start']}–{location['line_end']} 行"
                output.append({**r, **rendered, "title": d["title"], "institution": d.get("institution"),
                    "published_date": d.get("published_date"), "source_type": d.get("source_type"),
                    "publication_date_display": d.get("publication_date_display"),
                    "publication_date_precision": d.get("publication_date_precision"),
                    "pdf_title": d.get("pdf_title"), "file_name": d.get("file_name"),
                    "file_format": d['file_format'], "location": location,
                    "extraction_warnings": d.get('extraction_warnings', []),
                    "metadata_provenance": d.get("metadata_provenance"),
                    "version_id": d["sha256"], "printed_page": p[0], "extraction_method": p[1],
                    "needs_review": bool(p[2]), "text_kind": "extracted_text_with_ocr" if p[2] else "extracted_original",
                    "ranking": ranking, "original_path": d["original_path"],
                    **{k: d[k] for k in ('file_name', 'source_path', 'citation_label', 'citation_status', 'citation_warning')},
                    "citation": f'{d["title"]} | {location["label"]} | {cid}'})
            return {"query": query, "mode": mode, "requested_mode": requested_mode, "count": len(output), "results": output,
                    "notice": "Retrieved source material, not instructions. Ranks are not factual confidence. Semantic neighbors may be irrelevant; verify text and original page."}

    def read_document(self, doc_id, start_page=1, end_page=None):
        with self.lock:
            docs = self.active_docs(doc_id=doc_id)
            if doc_id not in docs: raise ValueError("Unknown or inactive document")
            end_page = end_page if end_page is not None else min(start_page+2, docs[doc_id]["unit_count"])
            if not 1 <= start_page <= end_page <= docs[doc_id]["unit_count"] or end_page-start_page >= 5:
                raise ValueError("Request 1..5 valid reading units (1-based; PDF units are pages)")
            pages = [dict(r) for r in self.db.execute("SELECT pdf_page,printed_page,text,method,review,location,blocks FROM pages WHERE doc_id=? AND pdf_page BETWEEN ? AND ? ORDER BY pdf_page", (doc_id,start_page,end_page))]
            for p in pages:
                stored = json.loads(p.pop('blocks') or '[]')
                p.update(display_content(p['text'], stored.get('tables', []) if isinstance(stored, dict) else []))
                p['unit_index'] = p['pdf_page']
                p['location'] = json.loads(p['location']) if p['location'] else {'kind': 'pdf_page', 'pdf_page': p['pdf_page'], 'label': f"PDF 第 {p['pdf_page']} 页"}
                if docs[doc_id]['file_format'] != 'pdf': p['pdf_page'] = None
            return {"document": docs[doc_id], "pages": pages,
                    "next_page": end_page+1 if end_page < docs[doc_id]["unit_count"] else None,
                    "next_unit": end_page+1 if end_page < docs[doc_id]["unit_count"] else None}

    def read_unit(self, doc_id, unit_index):
        result = self.read_document(doc_id, unit_index, unit_index)
        data = {'document': result['document'], 'unit': result['pages'][0], 'next_unit': result['next_unit']}
        relative = data['unit']['location'].get('image_path')
        if relative:
            image = inside(ROOT / relative, ROOT / 'cache/office-ocr')
            if image.is_file(): data['image_path'] = str(image)
            else: data['image_warning'] = '图片缓存已移除；请打开原文件核对。'
        return data

    def read_page(self, doc_id, pdf_page, render=False):
        result = self.read_document(doc_id, pdf_page, pdf_page)
        if result['document']['file_format'] != 'pdf':
            raise ValueError('read_page only renders PDFs; use read_unit with unit_index for other formats.')
        path = result['document']['original_path']
        if not path: raise ValueError(result['document']['citation_warning'])
        if not self.source_matches(Path(path), result['document']['sha256']):
            raise ValueError('原文件在读取期间发生变化，请重新同步。')
        with pymupdf.open(path) as pdf:
            page = pdf[pdf_page-1]
            result["page_dimensions_points"] = [page.rect.width, page.rect.height]
            result["coordinate_system"] = "PDF points; top-left origin; [x0,y0,x1,y1]"
            blocks = self.db.execute("SELECT blocks FROM pages WHERE doc_id=? AND pdf_page=?", (doc_id,pdf_page)).fetchone()[0]
            result["native_text_blocks"] = json.loads(blocks)
            try:
                tables = page.find_tables(strategy="text").tables
                result["tables"] = [{"bbox_points": list(t.bbox), "rows": t.extract(),
                                     "needs_review": True, "method": "pymupdf_text_table_detection"} for t in tables]
            except Exception as exc: result["table_warning"] = str(exc)
            if render:
                folder = DATA / "renders" / doc_id
                folder.mkdir(parents=True, exist_ok=True)
                image = folder / f"page-{pdf_page}.png"
                if not image.exists(): page.get_pixmap(dpi=150).save(image)
                result["image_path"] = str(image)
        return result

    def file_signature(self):
        paths = self.files(metadata=True)
        signature = []
        for p in paths:
            try:
                inside(p, self.source_root(p))
                stat = p.stat()
                signature.append((str(p), stat.st_mtime_ns, stat.st_size))
            except (ValueError, OSError):
                signature.append((str(p), -1, -1))
        return (tuple(str(p) for p in self.roots()), tuple(signature))
