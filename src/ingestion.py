"""Incremental import: bounded parser processes, short commits, reusable vectors."""
import hashlib
import json
import time
import array
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from paths import ROOT
from models import available
from document_formats import parser_version
from document_metadata import SCHEMA_VERSION
from resource_budget import parser_workers
from spooled import Spool


def run(library, retry=False, path=None):
    from library import digest, now, tokens
    from storage import fingerprint
    from office_ocr import cancelled
    from ingest_jobs import extract
    db, lock = library.db, library.lock
    stats = {'parsed': 0, 'unchanged': 0, 'embedded_chunks': 0, 'reused_vectors': 0,
             'parse_seconds': 0., 'hashing_seconds': 0., 'embedding_seconds': 0., 'commit_seconds': 0., 'workers': parser_workers()}
    started = time.monotonic()
    with lock:
        files = library.files()
        failed = {r[0] for r in db.execute("SELECT path FROM sources WHERE state IN ('failed','partial')")}
        if retry:
            if path is not None:
                if not isinstance(path, str) or path not in failed: raise ValueError('请选择导入失败或部分入库的文件')
                failed = {path}
            files = [p for p in files if str(p.absolute()) in failed]
            for missing in failed-{str(p.absolute()) for p in files}:
                db.execute("UPDATE sources SET state='missing',checked_at=? WHERE path=?", (now(), missing))
            db.commit()
    library.set_progress(stage='planning', file_total=len(files), file_index=0, workers=stats['workers'])
    # Plan outside write transactions. Fingerprints avoid rehashing unchanged files
    # on each polling cycle; changed size, mtime OR ctime invalidates the entry.
    plans = []
    for index, file in enumerate(files, 1):
        if library.sync_cancel.is_set(): break
        rel = str(file.absolute()); plan = {'path': file, 'rel': rel}
        try:
            from paths import inside
            inside(file, library.source_root(file))
            fp = json.dumps(fingerprint(file))
            with lock:
                cached = db.execute('SELECT fingerprint,sha FROM source_fingerprints WHERE path=?', (rel,)).fetchone()
            tick = time.monotonic()
            sha = cached['sha'] if cached and cached['fingerprint'] == fp else digest(file)
            stats['hashing_seconds'] += time.monotonic()-tick
            identity = sha if file.suffix.lower() == '.pdf' else hashlib.sha256((sha+file.suffix.lower()).encode()).hexdigest()
            doc_id = 'd_'+identity[:24]
            with lock:
                row = db.execute('SELECT metadata FROM documents WHERE doc_id=?', (doc_id,)).fetchone()
                meta = json.loads(row[0]) if row else None
                rebuild = bool(meta and file.suffix.lower() != '.pdf' and meta.get('parser_version') != parser_version(file.suffix))
                if meta:
                    rebuild |= retry and meta.get('partial', False)
                    rebuild |= meta.get('partial', False) and meta.get('large_file_mode', False) != library.settings().get('large_file_mode', False)
                    if file.suffix.lower() == '.pdf':
                        from pdf_ocr import VERSION
                        from pdf_text import is_notice
                        rebuild |= meta.get('partial', False) and meta.get('pdf_ocr_version') != VERSION
                        if meta.get('pdf_text_version', 0) < 1:
                            rebuild |= any(is_notice(r[0]) for r in db.execute('SELECT text FROM pages WHERE doc_id=?', (doc_id,)))
                    for r in db.execute('SELECT location FROM pages WHERE doc_id=?', (doc_id,)):
                        image = json.loads(r[0] or '{}').get('image_path')
                        if image and not inside(ROOT/image, ROOT/'cache/office-ocr').is_file(): rebuild = True
            plan.update(sha=sha, fingerprint=fp, doc_id=doc_id, meta=meta, rebuild=rebuild)
        except Exception as exc: plan['error'] = str(exc)
        plans.append(plan)
        library.set_progress(file_index=index)
    stats['planning_seconds'] = time.monotonic()-started
    results, pending = [], {}
    # At most N outstanding extractions (including completed results), bounding RAM
    # and scratch files even if the first workbook is much slower than the next.
    pool = ThreadPoolExecutor(max_workers=stats['workers'])
    cursor = 0
    def refill():
        nonlocal cursor
        while cursor < len(plans) and len(pending) < stats['workers'] and not library.sync_cancel.is_set():
            i = cursor; cursor += 1; p = plans[i]
            if 'error' not in p and (not p['meta'] or p['rebuild']):
                pending[i] = pool.submit(extract, library, p['path'], p['doc_id'])
    try:
        refill()
        for index, plan in enumerate(plans):
            if library.sync_cancel.is_set(): break
            file, rel = plan['path'], plan['rel']
            library.set_progress(stage='reading', file=file.name, file_index=index+1, file_total=len(files), image=None, location=None)
            pages = chunks = vectors = None
            try:
                if 'error' in plan: raise ValueError(plan['error'])
                doc_id, sha = plan['doc_id'], plan['sha']
                meta = plan['meta']
                needs_parse = meta is None or plan['rebuild']
                if needs_parse:
                    tick = time.monotonic()
                    # No database/model lock is held while waiting for parser workers.
                    meta, pages, chunks = pending.pop(index).result()
                    stats['parse_seconds'] += meta.pop('_parse_seconds', time.monotonic()-tick)
                    refill(); cancelled(library.sync_cancel)
                    stats['parsed'] += 1
                    vectors = Spool()
                    if available(library.embedding['model']) and chunks:
                        library.set_progress(stage='embedding')
                        tick = time.monotonic()
                        for offset in range(0, len(chunks), 64):
                            cancelled(library.sync_cancel)
                            batch = chunks[offset:offset+64]; keys = [hashlib.sha256(c[5].encode()).hexdigest() for c in batch]
                            found = {}
                            with lock:
                                for key in set(keys):
                                    r = db.execute('SELECT vector FROM embedding_cache WHERE model=? AND hash=?', (library.embedding['model'], key)).fetchone()
                                    if r:
                                        values = array.array('f'); values.frombytes(zlib.decompress(r[0])); found[key] = list(values)
                            # Reuse vectors already stored by older releases too, including
                            # unchanged paragraphs in a newly saved version of a document.
                            with lock:
                                previous = db.execute('SELECT doc_id FROM sources WHERE path=?', (rel,)).fetchone()
                                old_id = previous[0] if previous else doc_id
                                placeholders = ','.join('?' for _ in batch)
                                old_rows = db.execute(f'SELECT chunk_id,text FROM chunks WHERE doc_id=? AND text IN ({placeholders})', (old_id, *[c[5] for c in batch])).fetchall()
                                if old_rows:
                                    ids = [r[0] for r in old_rows]
                                    try:
                                        stored = library.vector_table().search().where("chunk_id IN ("+','.join("'"+i+"'" for i in ids)+")").select(['chunk_id','vector']).limit(len(ids)).to_list()
                                        by_id = {r['chunk_id']: r['vector'] for r in stored}
                                        for r in old_rows:
                                            if r[0] in by_id: found[hashlib.sha256(r[1].encode()).hexdigest()] = list(by_id[r[0]])
                                    except (ValueError, KeyError): pass
                            missing = list(dict.fromkeys(key for key in keys if key not in found))
                            if missing:
                                texts = {key: c[5] for key, c in zip(keys, batch)}
                                # Serialize model calls independently from database access.
                                with library.model_lock:
                                    computed = list(library.embedder().passage_embed([texts[k] for k in missing], batch_size=16))
                                found.update({key: v.tolist() for key, v in zip(missing, computed)})
                                stats['embedded_chunks'] += len(missing)
                                with lock:
                                    db.executemany('INSERT OR REPLACE INTO embedding_cache VALUES(?,?,?)', ((library.embedding['model'], key, zlib.compress(array.array('f', found[key]).tobytes(), 1)) for key in missing))
                                    db.execute('DELETE FROM embedding_cache WHERE rowid < (SELECT MAX(rowid)-32768 FROM embedding_cache)')
                                    db.commit()
                            stats['reused_vectors'] += len(batch)-len(missing)
                            vectors.extend({'chunk_id': c[0], 'doc_id': doc_id, 'vector': found[key]} for c, key in zip(batch, keys))
                        stats['embedding_seconds'] += time.monotonic()-tick
                    snapshot = library.snapshot_file(file, sha)
                    if digest(file) != sha: raise RuntimeError('File changed during indexing; retry after copy finishes')
                    tick = time.monotonic()
                    with lock:
                        if vectors:
                            table = library.vector_table(); table.delete(f"doc_id = '{doc_id}'")
                            for offset in range(0, len(vectors), 64): table.add(vectors[offset:offset+64])
                        # Duplicate paths share one document, including parallel completed jobs.
                        db.execute('DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_id=?)', (doc_id,))
                        db.execute('DELETE FROM chunks WHERE doc_id=?', (doc_id,)); db.execute('DELETE FROM pages WHERE doc_id=?', (doc_id,))
                        db.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?)', (doc_id, sha, snapshot, json.dumps(meta), len(pages), now()))
                        db.executemany('INSERT INTO pages VALUES(?,?,?,?,?,?,?,?)', pages)
                        db.executemany('INSERT INTO chunks VALUES(?,?,?,?,?,?)', chunks)
                        db.executemany('INSERT INTO chunks_fts VALUES(?,?)', ((c[0], ' '.join(tokens(c[5]))) for c in chunks))
                        db.commit()
                    stats['commit_seconds'] += time.monotonic()-tick
                else:
                    stats['unchanged'] += 1
                    # Metadata upgrades should not reparse Office bodies or recalculate vectors.
                    if file.suffix.lower() == '.pdf' and meta.get('metadata_schema_version', 0) < SCHEMA_VERSION:
                        import pymupdf
                        with pymupdf.open(file) as pdf: updated = library.metadata(file, pdf)
                        for key in ('institution', 'published_date', 'source_type', 'companies'):
                            if meta.get(key) and meta[key] != 'unclassified': updated[key] = meta[key]
                        meta = {**meta, **updated}
                    meta = library.metadata_overrides(file, meta)
                    if library.settings().get('keep_snapshots', False):
                        snapshot = library.snapshot_file(file, sha)
                        with lock: db.execute('UPDATE documents SET snapshot=? WHERE doc_id=?', (snapshot, doc_id))
                    with lock: db.execute('UPDATE documents SET metadata=? WHERE doc_id=?', (json.dumps(meta), doc_id))
                state = 'partial' if meta.get('partial') else 'skipped' if meta.get('no_searchable_text') else 'ready'
                note = '；'.join(meta.get('extraction_warnings', [])) if state == 'partial' else '已跳过：无可检索文字' if state == 'skipped' else None
                with lock:
                    db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?)', (rel, doc_id, state, note, now()))
                    db.execute('INSERT OR REPLACE INTO source_fingerprints VALUES(?,?,?)', (rel, plan['fingerprint'], sha))
                    db.commit()
                results.append({'file': rel, 'doc_id': doc_id, 'action': 'indexed' if needs_parse else 'unchanged_or_duplicate'})
            except InterruptedError: break
            except Exception as exc:
                with lock:
                    db.rollback(); db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?)', (rel, None, 'failed', str(exc), now())); db.commit()
                results.append({'file': rel, 'action': 'failed', 'error': str(exc)})
            finally:
                for spool in (pages, chunks, vectors):
                    if spool is not None: spool.close()
                refill()
    finally:
        if pending: library.sync_cancel.set()
        pool.shutdown(wait=True, cancel_futures=True)
        for future in pending.values():
            if not future.cancelled():
                try:
                    _, pages, chunks = future.result(); pages.close(); chunks.close()
                except Exception: pass
    with lock:
        if not retry and not library.sync_cancel.is_set():
            seen = {str(f.absolute()) for f in files}
            for row in db.execute('SELECT path FROM sources').fetchall():
                if row[0] not in seen: db.execute("UPDATE sources SET state='missing',checked_at=? WHERE path=?", (now(), row[0]))
            db.commit()
    stats['elapsed_seconds'] = time.monotonic()-started
    library.set_progress(metrics=stats)
    return {'results': results, 'cancelled': library.sync_cancel.is_set(), 'metrics': stats, 'status': library.status()}
