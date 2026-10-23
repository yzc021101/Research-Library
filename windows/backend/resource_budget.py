"""Conservative cross-platform concurrency; leave headroom for interactive work."""
import os
import subprocess
import sys
import re

def memory_gb():
    try:
        if os.name == 'nt':
            import ctypes
            class Memory(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in ('total', 'available', 'page', 'page_available', 'virtual', 'virtual_available', 'extended')]
            value = Memory(); value.length = ctypes.sizeof(value)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)): return 4
            return min(value.total, value.available) / 2**30
        if sys.platform == 'darwin':
            total = int(subprocess.check_output(['/usr/sbin/sysctl', '-n', 'hw.memsize'], timeout=2, stderr=subprocess.DEVNULL))
            vm = subprocess.check_output(['/usr/bin/vm_stat'], timeout=2, text=True, stderr=subprocess.DEVNULL)
            page_size = int(re.search(r'page size of (\d+)', vm).group(1))
            counts = dict((k, int(v)) for k, v in re.findall(r'([^\n:]+):\s+(\d+)\.', vm))
            available = sum(counts.get(k, 0) for k in ('Pages free', 'Pages inactive', 'Pages speculative'))*page_size
            return min(total, available)/2**30
        if hasattr(os, 'sysconf') and 'SC_AVPHYS_PAGES' in os.sysconf_names:
            return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / 2**30
        if hasattr(os, 'sysconf') and 'SC_PHYS_PAGES' in os.sysconf_names:
            return os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / 2**30
        return 4
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError): return 4

def parser_workers():
    return max(1, min(4, (os.cpu_count() or 2)//2, int(memory_gb()//3)))

def embedding_threads():
    return max(1, min(8, (os.cpu_count() or 2)//2, int(memory_gb())))
