"""All generated state belongs to this disposable laboratory directory."""
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent
PACKAGED = bool(getattr(sys, 'frozen', False))
def default_root():
    if os.name == 'nt': return Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))/'research_library'
    return Path.home()/'Library/Application Support/research_library'
ROOT = Path(os.environ.get('RESEARCH_LIBRARY_ROOT') or (default_root() if PACKAGED else SOURCE_ROOT.parent)).resolve()
for name in ('data', 'logs', 'inbox', 'tmp', 'components'):
    (ROOT/name).mkdir(parents=True, exist_ok=True)

def worker_command(module, *args):
    if PACKAGED: return [sys.executable, module, *map(str, args)]
    return [sys.executable, '-B', str(SOURCE_ROOT/(module+'.py')), *map(str, args)]

# Private optional OCR takes precedence; no edits to system installations.
ocr = ROOT/'components/ocr'
if (ocr/('tesseract.exe' if os.name == 'nt' else 'bin/tesseract')).is_file():
    os.environ['PATH'] = str(ocr if os.name == 'nt' else ocr/'bin') + os.pathsep + os.environ.get('PATH','')
    os.environ['TESSDATA_PREFIX'] = str(ocr/'tessdata')
for key, relative in {
    "TMPDIR": "tmp", "TEMP": "tmp", "TMP": "tmp", "XDG_CACHE_HOME": "cache", "XDG_STATE_HOME": "data/state",
    "HF_HOME": "cache/huggingface", "HF_HUB_CACHE": "cache/huggingface/hub",
    "HF_XET_CACHE": "cache/huggingface/xet", "FASTEMBED_CACHE_PATH": "cache/models",
    "UV_CACHE_DIR": "cache/uv", "MPLCONFIGDIR": "cache/matplotlib",
}.items():
    folder = ROOT / relative
    folder.mkdir(parents=True, exist_ok=True)
    os.environ[key] = str(folder)
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DO_NOT_TRACK"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"

INBOX = ROOT / "inbox"
DATA = ROOT / "data"
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

def inside(path: Path, parent: Path = ROOT) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(parent.resolve()):
        raise ValueError("Path escapes the laboratory directory")
    return resolved

for name in ("inbox", "logs", "data", "tmp"):
    (ROOT / name).mkdir(parents=True, exist_ok=True)

# Keep the OCR runtime and language data private to this installation.
OCR = ROOT.parent / "tools" / "tesseract"
if (OCR / "tesseract.exe").is_file():
    os.environ["PATH"] = str(OCR) + os.pathsep + os.environ.get("PATH", "")
    os.environ["TESSDATA_PREFIX"] = str(OCR / "tessdata")
