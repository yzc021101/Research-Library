"""Shared payload manifests for update validation and precise Windows uninstall."""
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
names=sorted({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} | {'installed-files.txt','distribution-files.json'})
(root/'installed-files.txt').write_text('\n'.join(names)+'\n',encoding='utf-8')
(root/'distribution-files.json').write_text(json.dumps([n for n in names if n!='distribution-files.json']),encoding='utf-8')
