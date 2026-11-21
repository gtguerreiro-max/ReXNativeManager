"""Tarefas em segundo plano (downloads, preparar/compilar/testar, Steam Deck), cada uma com o seu
registo em <data_dir>/logs/<id>.log e eventos para a interface. Correm em "faixas": downloads em
paralelo (max_downloads), compilações uma de cada vez (o PC fica ocupado), os relatórios numa pista
sua (report) e os jogos novos noutra (prepare), cada uma com a sua cópia do ReXNative, o Deck uma de
cada vez.
Cancelar mata só a árvore de processos da própria tarefa (taskkill /T), nunca outros processos.

A fila sobrevive a um reinício da app: uma tarefa em fila cujo tipo tem uma receita (Manager.resume:
tipo -> função(tarefa) -> fn) volta à fila quando a app abre. Para reiniciar (versions.restart_when_idle)
a app só espera pelas tarefas que estão a correr: as que estão em fila ficam para depois, e as que só
seguem outras ou só esperam (pedidos, um download, o Deck a dormir) devolvem a vez (Requeue)."""
import collections
import datetime
import json
import os
import secrets
import subprocess
import threading
import time
import traceback

from . import config, fsutil

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
# Jobs that only follow other jobs (a request from the Deck follows its download, its pipeline and
# its transfer): a restart of the app does not wait for them, and one that was running when the
# app closed starts again from what is already done.
FOLLOWERS = ('order', 'deck-report', 'deck-batch')
STATUS_PT = {'queued': 'queued', 'running': 'running', 'ok': 'done', 'failed': 'failed',
             'cancelled': 'cancelled', 'interrupted': 'interrupted'}


def now():
    return datetime.datetime.now().isoformat(timespec='seconds')


class Cancelled(Exception):
    pass


class Requeue(Exception):
    """The job gives its turn back: it is queued again and runs after the app restarts."""


class Job:
    manager = None  # o Manager da app (para dizer o que uma tarefa em fila espera)
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
        # Escrever ao assistente enquanto trabalha (claude._session, só com o Claude); None sem sessão aberta.
        self._say = None
        self._cancel = threading.Event()
        # True while the job only waits or can pick up where it stopped (a download, waiting for the
        # Deck): a restart of the app does not wait for it, it is queued again (Requeue).
        self.drain_stop = False

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
    def _draining(self):
        return bool(self.drain_stop and Job.manager is not None and Job.manager.draining and
                    Job.manager.resumable(self))

    def check(self):
        if self._cancel.is_set():
            raise Cancelled()
        if self._draining():
            raise Requeue()

    def sleep(self, seconds):
        end = time.time() + seconds
        while True:
            self.check()
            left = end - time.time()
            if left <= 0:
                return
            if self._cancel.wait(min(left, 2.0)):
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
                    if self._draining():
                        self.kill()
                        self.log('stopped for the restart of the app: it continues afterwards')
                        raise Requeue()
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
        d['chat'] = self._say is not None  # o assistente está a trabalhar e lê o que se lhe escreve
        if with_events:
            d['events'] = self.events[-200:]
        if progress and self.status == 'queued' and Job.manager is not None:
            d['waiting'] = Job.manager.waiting(self)
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
        j.saved_status = None
        if j.status in ('queued', 'running'):
            # Manager.resume puts back in the queue the ones it has a recipe for.
            j.saved_status = j.status
            j.status = 'interrupted'
            j.error = 'the app closed before the job finished'
        return j


class Manager:
    LANES = {'download': None, 'build': 1, 'report': 1, 'prepare': 1, 'deck': 1, 'quick': 3, 'orders': 6}

    def __init__(self):
        Job.manager = self
        self.jobs = {}
        self.lock = threading.RLock()  # re-entrant: a recipe may look at the job list
        self.file_lock = threading.Lock()
        # Each lane: the jobs waiting for a turn, in order. One condition for all of them.
        self.pending = {lane: [] for lane in self.LANES}
        self.cv = threading.Condition(self.lock)
        # The app wants to restart: no job that can continue afterwards starts (resumable), and
        # stopped is set, under the lock, once nothing runs: from then on nothing starts at all.
        self.draining = False
        self.stopped = False
        self.recipes = {}  # kind -> function(job) -> fn or None (Manager.resume)
        self.game_locks = {}
        self.held = {}  # lane -> the job that has it closed (Manager.alone)
        self.path = os.path.join(config.data_dir(), 'jobs.json')
        self._load()
        for lane, n in self.LANES.items():
            n = n or max(1, int(config.load()['max_downloads']))
            for _ in range(n):
                threading.Thread(target=self._worker, args=(lane,), daemon=True).start()

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
        with self.cv:
            self.jobs[j.id] = j
            self.pending[lane].append(j)
            self.cv.notify_all()
        j.log('%s - %s (%s)' % (j.created, title, kind))
        self.save()
        return j

    # -- a fila depois de um reinício ---------------------------------------------------------
    def resumable(self, j):
        """Whether this job can run after a restart of the app: its kind has a recipe that makes
        its function again from what the job saved (params, result)."""
        make = self.recipes.get(j.kind)
        try:
            return bool(make) and make(j) is not None
        except Exception:  # noqa: BLE001 - a recipe that fails is no recipe
            return False

    def resume(self, recipes):
        """recipes: kind -> function(job) -> fn (or None when the job did not save enough). The
        jobs that were queued when the app closed go back in their queues, in order, and so do
        the FOLLOWERS that were running (they only follow other jobs). Returns how many."""
        self.recipes = dict(recipes)
        back = []
        with self.lock:
            items = sorted(self.jobs.values(), key=lambda j: j.created)
        for j in items:
            saved = getattr(j, 'saved_status', None)
            if saved != 'queued' and not (saved == 'running' and j.kind in FOLLOWERS):
                continue
            make = self.recipes.get(j.kind)
            try:
                fn = make(j) if make else None
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                fn = None
            if fn is None:
                continue
            j._fn = fn
            j.status, j.error, j.started, j.ended = 'queued', None, None, None
            j.saved_status = None
            j.event('info', 'Back in the queue: the app restarted')
            back.append(j)
        with self.cv:
            for j in back:
                self.pending[j.lane].append(j)
            self.cv.notify_all()
        if back:
            self.save()
        return len(back)

    def drain(self):
        """The app wants to restart: from now on only the jobs that could not continue afterwards
        start. Returns True, with stopped set, once nothing runs and none of those waits."""
        with self.cv:
            self.draining = True
            self.cv.notify_all()
            if any(j.status == 'running' for j in self.jobs.values()):
                return False
            if any(j.status == 'queued' and not self.resumable(j) for j in self.jobs.values()):
                return False
            self.stopped = True
        return True

    def drain_state(self):
        """(what a pending restart waits for, what continues after it), two lists of jobs."""
        with self.lock:
            items = sorted(self.jobs.values(), key=lambda j: j.created)
        later = [j for j in items if (j.status == 'queued' or (
            j.status == 'running' and (j.drain_stop or j.kind in FOLLOWERS))) and self.resumable(j)]
        first = [j for j in items if j.status in ('queued', 'running') and j not in later]
        return first, later

    def game_lock(self, slug):
        """One job at a time builds or tests a game, whatever the lane (a report in its lane, a
        pipeline or a suspects batch in the build lane)."""
        with self.lock:
            return self.game_locks.setdefault(slug, threading.Lock())

    def alone(self, job, lanes):
        """A context for a job that cannot run beside the jobs of other lanes (the SDK update: no
        game may build meanwhile, in the report lane either): those lanes start nothing while it
        lasts, and it begins once nothing runs in them."""
        manager = self

        class _Alone:
            def __enter__(self):
                with manager.cv:
                    for lane in lanes:
                        manager.held[lane] = job
                said = False
                while True:
                    with manager.lock:
                        busy = [j for j in manager.jobs.values() if j.status == 'running' and
                                j.lane in lanes and j is not job]
                    if not busy:
                        return self
                    if not said:
                        job.event('info', 'Waiting for %s to finish' % busy[0].title)
                        said = True
                    try:
                        job.sleep(2)
                    except BaseException:
                        self.__exit__()
                        raise

            def __exit__(self, *exc):
                with manager.cv:
                    for lane in lanes:
                        if manager.held.get(lane) is job:
                            del manager.held[lane]
                    manager.cv.notify_all()
        return _Alone()

    def _next(self, lane):
        """The next job of this lane to run (blocks): (job, True), marked running, or (job, False)
        for one cancelled while it waited. While the app waits to restart, a job that can
        continue afterwards stays where it is."""
        with self.cv:
            while True:
                if not self.stopped and lane not in self.held:
                    for j in self.pending[lane]:
                        if j._cancel.is_set() or j.status != 'queued':
                            self.pending[lane].remove(j)
                            return j, False
                        # The recipes only read the job and the state: called with the lock held,
                        # so holding a job here and drain's last look agree.
                        if self.draining and self.resumable(j):
                            continue
                        self.pending[lane].remove(j)
                        j.status = 'running'
                        j.started = now()
                        return j, True
                self.cv.wait(1.0)

    def _worker(self, lane):
        # O fio nunca morre: um erro fora da tarefa marca-a como falhada e segue para a próxima.
        while True:
            j, go = self._next(lane)
            try:
                self._run_one(j, go)
            except BaseException as e:  # noqa: BLE001 - SystemExit do rexnative incluído
                traceback.print_exc()
                j.status = 'failed'
                j.error = 'internal app error: %s' % e
                j.ended = j.ended or now()

    def _run_one(self, j, go=True):
        if not go:
            if j.status == 'queued':
                j.status = 'cancelled'
                j.ended = now()
                self.save()
            return
        self.save()
        try:
            res = j._fn(j)
            if isinstance(res, dict):
                j.result.update(res)
            j.status = 'ok'
        except Requeue:
            # It gave its turn back for the restart of the app: queued again, as it was.
            j.progress = None
            j.started = None
            j.status = 'queued'
            j.event('info', 'Waiting for the app to restart: it continues afterwards')
        except Cancelled:
            j.status = 'cancelled'
            j.event('fail', 'Cancelled by the user')
        except Exception as e:  # noqa: BLE001 - a tarefa falha, a app continua
            j.status = 'failed'
            j.error = str(e) or type(e).__name__
            j.log(traceback.format_exc())
            j.event('fail', j.error)
        finally:
            if j.status != 'queued':
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

    def waiting(self, j):
        """Uma tarefa em fila: o que corre agora na sua pista (uma de cada vez nas compilações e no Deck)
        e quantas estão à frente dela; None se não está à espera de nada."""
        if j is None or j.status != 'queued':
            return None
        with self.lock:
            same = [x for x in self.jobs.values() if x.lane == j.lane and x is not j]
        running = sorted((x for x in same if x.status == 'running'), key=lambda x: x.started or '')
        ahead = sum(1 for x in same if x.status == 'queued' and x.created <= j.created)
        # A restart of the app is pending and this job runs after it.
        later = self.draining and self.resumable(j)
        if not running and not ahead and not later:
            return None
        out = {'lane': j.lane, 'ahead': ahead, 'running': len(running)}
        if later:
            out['restart'] = True
        if running:
            r = running[0]
            try:
                secs = max(0, time.time() - datetime.datetime.fromisoformat(r.started).timestamp())
            except (TypeError, ValueError):
                secs = None
            out.update(job=r.id, title=r.title, kind=r.kind, game=r.game, for_s=secs)
        return out

    def forget(self, statuses):
        """Tira da lista as tarefas acabadas com estes estados (nunca uma em fila ou a correr); os
        registos delas ficam em logs/. Devolve quantas."""
        statuses = set(statuses) - {'queued', 'running'}
        with self.lock:
            gone = [i for i, j in self.jobs.items() if j.status in statuses]
            for i in gone:
                del self.jobs[i]
        if gone:
            self.save()
        return len(gone)

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
