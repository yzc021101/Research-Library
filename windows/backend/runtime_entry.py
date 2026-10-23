import multiprocessing
import runpy
import sys
if __name__ == '__main__':
    multiprocessing.freeze_support()
    import encodings.idna, encodings.punycode, stringprep
    from runtime_pin import pin_server
    if len(sys.argv)>1 and sys.argv[1]=='prepare_mcp':
        from runtime_pin import prepare_launcher_runtime
        prepare_launcher_runtime()
        raise SystemExit(0)
    if sys.platform=='win32' and len(sys.argv)>1 and sys.argv[1] in ('backend','check_mcp'):
        from runtime_pin import write_windows_launcher
        write_windows_launcher()
    pin_server()
    from windows_runtime import prepare_runtime_aliases
    prepare_runtime_aliases()
    modes = {'backend', 'server', 'model_worker', 'embedding_worker', 'settings_cli', 'check_mcp', 'package_smoke', 'updater', 'ingest_worker'}
    mode = sys.argv.pop(1) if len(sys.argv)>1 else 'server'
    if mode not in modes: raise SystemExit('Unknown runtime mode')
    runpy.run_module(mode, run_name='__main__')
