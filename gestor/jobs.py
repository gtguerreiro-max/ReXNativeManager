"""Tarefas em segundo plano (downloads, preparar/compilar/testar, Steam Deck), cada uma com o seu
registo em <data_dir>/logs/<id>.log e eventos para a interface. Correm em "faixas": downloads em
paralelo (max_downloads), compilações uma de cada vez (o PC fica ocupado), o Deck uma de cada vez.
Cancelar mata só a árvore de processos da própria tarefa (taskkill /T), nunca outros processos."""
import collections
import datetime
import json
import os
import queue
import secrets
import subprocess
import threading
import time
import traceback

from . import config, fsutil

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
STATUS_PT = {'queued': 'queued', 'running': 'running', 'ok': 'done', 'failed': 'failed',
             'cancelled': 'cancelled', 'interrupted': 'interrupted'}


def now():
    return datetime.datetime.now().isoformat(timespec='seconds')


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, kind, title, lane, fn=None, game=None, params=None):
        self.id = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(2)
        self.kind = kind
        self.title = title
        self.lane = lane
        self.game = game
        self.params = params or {}
        self.status = 'queued'
        self.created = now()
        self.started = None
        self.ended = None
        self.error = None
        self.result = {}
        self.events = []
        self.progress = None  # função sem argumentos -> {'done': n, 'total': n} (ou dict)
        self.log_path = os.path.join(config.data_dir('logs'), self.id + '.log')
        self._fn = fn
        self._proc = None
        self._cancel = threading.Event()

    # -- registo ---------------------------------------------------------------------------
    def log(self, text):
        with open(self.log_path, 'a', encoding='utf-8', errors='replace', newline='\n') as f:
            f.write(text if text.endswith('\n') else text + '\n')

    def event(self, kind, text, **data):
        """Um passo para a interface (step, ok, fail, claude, info) e o mesmo no registo."""
        e = dict(t=now(), kind=kind, text=text, **data)
        self.events.append(e)
        self.log('[%s] %s %s' % (e['t'], kind.upper(), text))
        return e

    # -- processos -------------------------------------------------------------------------
    def check(self):
        if self._cancel.is_set():
            raise Cancelled()

    def sleep(self, seconds):
        if self._cancel.wait(seconds):
            raise Cancelled()

    def run(self, cmd, cwd=None, env=None, log_path=None, timeout=None):
        """Corre cmd com a saída no registo (ou em log_path, que também fica no da tarefa no
        fim); devolve o código de saída. Cancelar mata a sua árvore de processos."""
        self.check()
        shown = ' '.join('"%s"' % c if ' ' in str(c) else str(c) for c in cmd)
        self.log('$ %s%s' % (shown, ('    (in %s)' % cwd) if cwd else ''))
        out_path = log_path or self.log_path
        t0 = time.time()
        with open(out_path, 'ab') as out:
            self._proc = subprocess.Popen(
                [str(c) for c in cmd], cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else 0)
            try:
                while True:
                    try:
                        rc = self._proc.wait(0.5)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    if self._cancel.is_set():
                        self.kill()
                        raise Cancelled()
                    if timeout and time.time() - t0 > timeout:
                        self.log('timed out (%d s): process killed' % timeout)
                        self.kill()
                        return -1
            finally:
                self._proc = None
        if log_path and log_path != self.log_path:
            self.log('(full output in %s)' % log_path)
        self.log('-> exit code %d (%.0f s)' % (rc, time.time() - t0))
        return rc

    def kill(self):
        p = self._proc
        if p and p.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'],
                               capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                p.kill()

    def cancel(self):
        self._cancel.set()
        self.kill()

    # -- estado ----------------------------------------------------------------------------
    def to_dict(self, with_events=True, progress=True):
        d = {k: getattr(self, k) for k in ('id', 'kind', 'title', 'lane', 'game', 'status', 'created',
                                            'started', 'ended', 'error', 'log_path')}
        # Cópias: o fio da tarefa vai juntando chaves a result e params enquanto isto se grava.
        d['params'] = dict(self.params) if isinstance(self.params, dict) else self.params
        d['result'] = dict(self.result) if isinstance(self.result, dict) else self.result
        d['status_pt'] = STATUS_PT.get(self.status, self.status)
        if with_events:
            d['events'] = self.events[-200:]
        if progress and self.status == 'running' and callable(self.progress):
            try:
                d['progress'] = self.progress()
            except Exception:
                d['progress'] = None
        elif isinstance(self.progress, dict):
            d['progress'] = self.progress
        return d

    @classmethod
    def from_dict(cls, d):
        j = cls.__new__(cls)
        j.__init__(d['kind'], d['title'], d['lane'], game=d.get('game'), params=d.get('params'))
        for k in ('id', 'status', 'created', 'started', 'ended', 'error', 'result', 'log_path'):
            setattr(j, k, d.get(k))
        j.events = d.get('events', [])
        if j.status in ('queued', 'running'):
            j.status = 'interrupted'
            j.error = 'the app closed before the job finished'
        return j


class Manager:
    LANES = {'download': None, 'build': 1, 'deck': 1, 'quick': 3, 'orders': 6}

    def __init__(self):
        self.jobs = {}
        self.lock = threading.Lock()
        self.file_lock = threading.Lock()
        self.queues = {}
        self.path = os.path.join(config.data_dir(), 'jobs.json')
        self._load()
        for lane, n in self.LANES.items():
            n = n or max(1, int(config.load()['max_downloads']))
            q = queue.Queue()
            self.queues[lane] = q
            for _ in range(n):
                threading.Thread(target=self._worker, args=(q,), daemon=True).start()

    def _load(self):
        if os.path.exists(self.path):
            try:
                for d in json.load(open(self.path, encoding='utf-8')):
                    j = Job.from_dict(d)
                    self.jobs[j.id] = j
            except (OSError, ValueError, KeyError):
                pass

    def save(self):
        """Grava jobs.json. Várias tarefas gravam ao mesmo tempo: um cadeado só para o ficheiro
        (no Windows, os.replace falha se outro fio tiver o .tmp aberto) e, se o antivírus ou um
        leitor o tiverem aberto, umas tentativas. Uma falha aqui nunca pára uma tarefa."""
        try:
            with self.lock:
                items = sorted(self.jobs.values(), key=lambda j: j.created)[-300:]
            # Um dicionário dentro de result pode mudar enquanto se converte: outra vez.
            for i in range(5):
                try:
                    text = json.dumps([j.to_dict(progress=False) for j in items], ensure_ascii=False,
                                      indent=0, default=str)
                    break
                except RuntimeError:
                    if i == 4:
                        raise
                    time.sleep(0.05)
            with self.file_lock:
                fsutil.write_text(self.path, text)
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    def submit(self, kind, title, fn, lane='build', game=None, params=None):
        j = Job(kind, title, lane, fn, game=game, params=params)
        with self.lock:
            self.jobs[j.id] = j
        j.log('%s - %s (%s)' % (j.created, title, kind))
        self.queues[lane].put(j)
        self.save()
        return j

    def _worker(self, q):
        # O fio nunca morre: um erro fora da tarefa marca-a como falhada e segue para a próxima.
        while True:
            j = q.get()
            try:
                self._run_one(j)
            except BaseException as e:  # noqa: BLE001 - SystemExit do rexnative incluído
                traceback.print_exc()
                j.status = 'failed'
                j.error = 'internal app error: %s' % e
                j.ended = j.ended or now()

    def _run_one(self, j):
        if j._cancel.is_set():
            j.status = 'cancelled'
            j.ended = now()
            self.save()
            return
        j.status = 'running'
        j.started = now()
        self.save()
        try:
            res = j._fn(j)
            if isinstance(res, dict):
                j.result.update(res)
            j.status = 'ok'
        except Cancelled:
            j.status = 'cancelled'
            j.event('fail', 'Cancelled by the user')
        except Exception as e:  # noqa: BLE001 - a tarefa falha, a app continua
            j.status = 'failed'
            j.error = str(e) or type(e).__name__
            j.log(traceback.format_exc())
            j.event('fail', j.error)
        finally:
            if callable(j.progress):
                try:
                    j.progress = j.progress()
                except Exception:
                    j.progress = None
            j.ended = now()
            self.save()

    def get(self, job_id):
        return self.jobs.get(job_id)

    def list(self, game=None, limit=100):
        with self.lock:
            items = sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)
        if game:
            items = [j for j in items if j.game == game]
        return items[:limit]

    def active(self, kind=None, game=None):
        return [j for j in self.list(limit=1000) if j.status in ('queued', 'running') and
                (kind is None or j.kind == kind) and (game is None or j.game == game)]

    def cancel(self, job_id):
        j = self.jobs.get(job_id)
        if j and j.status in ('queued', 'running'):
            j.cancel()
            if j.status == 'queued':
                j.status = 'cancelled'
                j.ended = now()
            self.save()
            return True
        return False


def read_log(path, offset=0, limit=200000):
    """(texto, novo offset) a partir de offset bytes."""
    if not path or not os.path.exists(path):
        return '', offset
    size = os.path.getsize(path)
    if offset > size:
        offset = 0
    with open(path, 'rb') as f:
        f.seek(offset)
        data = f.read(limit)
    return data.decode('utf-8', 'replace'), offset + len(data)


def with_rate(fn, window=20):
    """fn() -> {'done', 'total'} (bytes) com 'rate' (bytes/s nos últimos window s) e 'eta' (s que
    faltam), a partir das leituras de quem pergunta (a página, de poucos em poucos segundos).
    Recomeça quando done volta atrás ou o total muda (outra cópia)."""
    samples = collections.deque()
    lock = threading.Lock()

    def f():
        p = fn()
        if not p or not p.get('total'):
            return p
        now = time.time()
        with lock:
            if samples and (p['done'] < samples[-1][1] or p['total'] != samples[-1][2]):
                samples.clear()
            samples.append((now, p['done'], p['total']))
            while len(samples) > 2 and now - samples[0][0] > window:
                samples.popleft()
            t0, d0, _ = samples[0]
        if now - t0 >= 2 and p['done'] > d0:
            rate = (p['done'] - d0) / (now - t0)
            p = dict(p, rate=rate, eta=max(0.0, (p['total'] - p['done']) / rate))
        return p
    return f


def tail(path, lines=200):
    if not path or not os.path.exists(path):
        return ''
    with open(path, 'rb') as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 256 * 1024))
        data = f.read().decode('utf-8', 'replace')
    return '\n'.join(data.splitlines()[-lines:])
