"""Isolated parser process: no shared SQLite connection or PyMuPDF threads."""
import json
import os
import sys
import threading
from pathlib import Path

def main():
    os.environ['OMP_THREAD_LIMIT'] = '1'
    from library import Library
    folder = Path(sys.argv[1])
    job = json.loads((folder/'job.json').read_text(encoding='utf-8'))
    parser = Library.__new__(Library)
    parser.settings_provider = lambda: job['settings']
    parser.sync_cancel = threading.Event()
    parser.progress_lock = threading.Lock()
    parser.sync_progress = {}
    def progress(**values):
        parser.sync_progress.update(values)
        temp = folder/'progress.tmp'
        temp.write_text(json.dumps(parser.sync_progress), encoding='utf-8')
        try:
            temp.replace(folder/'progress.json')
        except PermissionError:
            # Windows can briefly hold the previous progress file open in the
            # reader. Progress is advisory; a later update can replace it.
            pass
    parser.set_progress = progress
    try:
        metadata, pages, chunks = parser.extract(Path(job['path']), job['doc_id'])
        for name, rows in [('pages', pages), ('chunks', chunks)]:
            with (folder/(name+'.jsonl')).open('w', encoding='utf-8') as out:
                for row in rows: out.write(json.dumps(row, ensure_ascii=False)+'\n')
        result = {'metadata': metadata}
    except Exception as exc:
        result = {'error': str(exc)}
    (folder/'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')

if __name__ == '__main__': main()
