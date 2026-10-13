"""Persist validated settings while the desktop service is stopped."""
import json
import sys
from settings import save_settings

if __name__ == "__main__":
    try:
        print(json.dumps(save_settings(json.load(sys.stdin)), ensure_ascii=False))
    except (ValueError, OSError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
