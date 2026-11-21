"""python -m gestor [--port N] [--no-browser]: a app em http://127.0.0.1:<porta>."""
import argparse
import os
import sys
import threading
import time
import webbrowser

LOG_MAX = 2 * 1024 * 1024  # acima disto, o registo passa a server.log.1 quando a app arranca


class _Tee:
    """O que a app escreve no ecrã (erros, tracebacks dos fios, avisos do uvicorn) vai também para
    <data_dir>/logs/server.log, com a hora em cada linha: depois de reiniciada pela própria app, ela
    corre escondida e, sem isto, um erro perdia-se."""

    def __init__(self, stream, f, lock):
        self.stream, self.f, self.lock = stream, f, lock
        self.bol = True

    def write(self, s):
        if self.stream is not None:
            try:
                self.stream.write(s)
            except (OSError, ValueError, UnicodeError):
                pass
        if not s:
            return 0
        with self.lock:
            try:
                out = []
                for line in s.splitlines(keepends=True):
                    if self.bol:
                        out.append(time.strftime('[%Y-%m-%d %H:%M:%S] '))
                    out.append(line)
                    self.bol = line.endswith('\n')
                self.f.write(''.join(out))
                self.f.flush()
            except (OSError, ValueError):
                pass
        return len(s)

    def flush(self):
        for x in (self.stream, self.f):
            try:
                if x is not None:
                    x.flush()
            except (OSError, ValueError):
                pass

    def isatty(self):
        return False

    def __getattr__(self, name):  # encoding, fileno, ... do original
        return getattr(self.stream, name)


def server_log_path():
    from . import config
    return os.path.join(config.data_dir(), 'logs', 'server.log')


def _log_to_file():
    path = server_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX:
            os.replace(path, path + '.1')
        f = open(path, 'a', encoding='utf-8', errors='replace')
    except OSError:
        return
    lock = threading.Lock()
    sys.stdout = _Tee(sys.stdout, f, lock)
    sys.stderr = _Tee(sys.stderr, f, lock)


def main():
    from . import config, version
    ap = argparse.ArgumentParser(prog='gestor')
    ap.add_argument('--port', type=int, default=config.load()['port'])
    ap.add_argument('--no-browser', action='store_true')
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    _log_to_file()
    os.chdir(config.ROOT)
    import uvicorn
    url = 'http://127.0.0.1:%d/' % a.port
    print('Gestor ReXNative %s em %s (pid %d; Ctrl+C fecha)' % (version.VERSION, url, os.getpid()))
    if not a.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run('gestor.app:app', host='127.0.0.1', port=a.port, log_level='warning')


if __name__ == '__main__':
    main()
