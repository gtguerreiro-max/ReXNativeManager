"""python -m gestor [--port N] [--no-browser]: a app em http://127.0.0.1:<porta>."""
import argparse
import os
import sys
import threading
import webbrowser


def main():
    from . import config
    ap = argparse.ArgumentParser(prog='gestor')
    ap.add_argument('--port', type=int, default=config.load()['port'])
    ap.add_argument('--no-browser', action='store_true')
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    os.chdir(config.ROOT)
    import uvicorn
    url = 'http://127.0.0.1:%d/' % a.port
    print('Gestor ReXNative em %s (Ctrl+C fecha)' % url)
    if not a.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run('gestor.app:app', host='127.0.0.1', port=a.port, log_level='warning')


if __name__ == '__main__':
    main()
