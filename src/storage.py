"""Source citations and bounded, private caches. Never writes to source folders."""
from paths import ROOT, DATA, inside
from pathlib import Path
from datetime import datetime, timezone, timedelta
import hashlib
import os
import shutil
import time


def fingerprint(path):
    s = path.stat()
    return (s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


class StorageMixin:
    def source_matches(self, path, sha):
        try:
            key = (str(path), fingerprint(path))
            if not hasattr(self, '_source_hashes'): self._source_hashes = {}
            if key not in self._source_hashes:
                value = file_hash(path)
                if fingerprint(path) != key[1]: return False
                # Bound memory during long editing sessions.
                if len(self._source_hashes) > 2048: self._source_hashes.clear()
                self._source_hashes[key] = value
            return self._source_hashes[key] == sha
        except OSError: return False

    def snapshot_file(self, path, sha):
        if not self.settings().get('keep_snapshots', False): return ''
        folder = DATA/'originals'/sha
        folder.mkdir(parents=True, exist_ok=True)
        target = folder/path.name
        if not target.exists():
            temp = folder/(path.name+'.tmp')
            try:
                shutil.copyfile(path, temp)
                if file_hash(temp) != sha: raise RuntimeError('File changed during snapshot creation')
                os.replace(temp, target)
            finally: temp.unlink(missing_ok=True)
        return str(target.relative_to(ROOT))

    def citation_info(self, row, paths):
        paths = sorted(paths, key=lambda p: str(p).casefold())
        valid = next((p for p in paths if self.source_matches(p, row['sha256'])), None)
        source = valid or next((p for p in paths if p.is_file()), paths[0] if paths else None)
        name = source.name if source else '原文不可用'
        info = {'file_name': name, 'source_path': str(source) if source else None,
                'original_path': str(valid) if valid else None,
                'citation_status': 'current' if valid else 'source_changed_or_missing',
                'citation_warning': None, 'citation_label': name}
        if valid: return info
        info['citation_warning'] = '原文件已修改或不可用；以下内容属于已录入版本。请同步后引用最新原文。'
        if row['snapshot']:
            try:
                saved = inside(ROOT/row['snapshot'], DATA/'originals')
                if saved.is_file() and self.source_matches(saved, row['sha256']):
                    # Existing hash-named snapshots keep their old links. A hard link
                    # supplies a human filename without duplicating file contents.
                    if saved.name != name and source:
                        alias = DATA/'originals'/row['sha256']/name
                        alias.parent.mkdir(parents=True, exist_ok=True)
                        if not alias.exists(): os.link(saved, alias)
                        saved = alias
                    info.update(original_path=str(saved), citation_status='snapshot',
                                citation_warning='原文件已修改或不可用；链接指向录入时的快照，并非当前原文件。')
            except (OSError, ValueError): pass
        return info

    def _cache_files(self, relative):
        base = ROOT/relative
        if not base.exists() or base.is_symlink(): return []
        return [p for p in base.rglob('*') if p.is_file() and not p.is_symlink()
                and p.resolve().is_relative_to(base.resolve())]

    def storage_status(self):
        with self.lock:
            categories = {}
            groups = {'snapshots': ['data/originals'], 'index': ['data/library.sqlite3', 'data/vectors'],
                      'previews': ['data/renders', 'cache/office-ocr'], 'conversions': ['cache/legacy-office'],
                      'models': ['cache/models', 'cache/model-packages'], 'components': ['components']}
            for name, folders in groups.items():
                files = []
                for f in folders:
                    p = ROOT/f
                    files.extend([p] if p.is_file() else self._cache_files(f))
                seen, size = set(), 0
                for p in files:
                    try:
                        s = p.stat(); key = (s.st_dev, s.st_ino)
                        if key not in seen: size += s.st_size; seen.add(key)
                    except OSError: pass
                categories[name] = {'bytes': size, 'files': len(files)}
            return {'categories': categories, 'total_bytes': sum(x['bytes'] for x in categories.values()),
                    'keep_snapshots': self.settings().get('keep_snapshots', False),
                    'cache_retention_days': self.settings().get('cache_retention_days', 30)}

    def cleanup_storage(self, mode='expired'):
        if mode not in ('expired', 'generated', 'snapshots'): raise ValueError('Unknown cleanup mode')
        with self.lock:
            cfg = self.settings(); cutoff = time.time()-cfg.get('cache_retention_days', 30)*86400
            roots = self.roots()
            active = {r['doc_id'] for r in self.db.execute("SELECT path,doc_id FROM sources WHERE state='ready'")
                      if any(Path(r['path']).resolve().is_relative_to(root) for root in roots)}
            rows = list(self.db.execute('SELECT doc_id,sha256,snapshot,indexed_at FROM documents'))
            protected = {r['sha256'] for r in rows if r['doc_id'] in active} if cfg.get('keep_snapshots', False) else set()
            removed = 0; size = 0; errors = []
            def remove(p):
                nonlocal removed, size
                try:
                    s = p.stat(); p.unlink(); removed += 1
                    if s.st_nlink == 1: size += s.st_size
                except OSError as exc: errors.append(str(exc))
            if mode in ('expired', 'snapshots'):
                for p in self._cache_files('data/originals'):
                    sha = p.parent.name if len(p.parent.name) == 64 else p.stem
                    if mode == 'snapshots' or (sha not in protected and p.stat().st_mtime < cutoff): remove(p)
                for r in rows:
                    if r['snapshot'] and not (ROOT/r['snapshot']).is_file():
                        self.db.execute('UPDATE documents SET snapshot=? WHERE doc_id=?', ('', r['doc_id']))
            if mode in ('expired', 'generated'):
                for relative in ('data/renders', 'cache/office-ocr', 'cache/legacy-office'):
                    for p in self._cache_files(relative):
                        if mode == 'generated' or p.stat().st_mtime < cutoff: remove(p)
            # Drop only obsolete, expired index versions, keeping current text even
            # when the original is temporarily on an unavailable external volume.
            if mode == 'expired':
                for r in rows:
                    if r['doc_id'] in active: continue
                    try: old = datetime.fromisoformat(r['indexed_at']).timestamp() < cutoff
                    except (ValueError, TypeError): old = False
                    if not old: continue
                    did = r['doc_id']
                    self.db.execute('DELETE FROM chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_id=?)', (did,))
                    for table in ('chunks', 'pages', 'documents'): self.db.execute(f'DELETE FROM {table} WHERE doc_id=?', (did,))
                    if (DATA/'vectors').exists():
                        try: self.vectors().open_table(self.embedding['table']).delete(f"doc_id = '{did}'")
                        except Exception as exc: errors.append('旧向量清理失败：'+str(exc))
            if mode == 'expired' and (DATA/'vectors').exists():
                try:
                    # Retain recent LanceDB history; current version is never removed.
                    self.vectors().open_table(self.embedding['table']).optimize(
                        cleanup_older_than=timedelta(days=cfg.get('cache_retention_days', 30)))
                except Exception as exc: errors.append('向量缓存整理失败：'+str(exc))
            self.db.commit()
            # SQLite compaction runs only on explicit/periodic cleanup, never search.
            if mode == 'expired': self.db.execute('VACUUM')
            for relative in ('data/originals', 'data/renders', 'cache/office-ocr', 'cache/legacy-office'):
                for p in sorted((ROOT/relative).rglob('*'), key=lambda p: len(p.parts), reverse=True):
                    if p.is_dir() and not p.is_symlink():
                        try: p.rmdir()
                        except OSError: pass
            return {'removed_files': removed, 'released_bytes': size, 'errors': errors, 'storage': self.storage_status()}
