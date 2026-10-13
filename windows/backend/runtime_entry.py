import multiprocessing
import runpy
import sys
if __name__ == '__main__':
    multiprocessing.freeze_support()
    from windows_runtime import prepare_runtime_aliases
    prepare_runtime_aliases()
    modes = {'backend', 'server', 'model_worker', 'settings_cli', 'check_mcp', 'package_smoke'}
    mode = sys.argv.pop(1) if len(sys.argv)>1 else 'server'
    if mode not in modes: raise SystemExit('Unknown runtime mode')
    runpy.run_module(mode, run_name='__main__')
