"""Tests of what goes once a game is prepared and built (gestor/tidy.py), and of an order for a game
whose archive went (gestor/orders.py), with made-up game folders:

    python scripts/test_tidy.py

Runs in a scratch folder (GESTOR_CONFIG points at a config made here): nothing of the app's own
data is read or written, and gestor.app is not imported (it would start the servers)."""
import json
import os
import shutil
import stat
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='gestor-test-')
OWN = os.path.join(TMP, 'own')
DL = os.path.join(TMP, 'downloads')
WORK = os.path.join(TMP, 'work')
with open(os.path.join(TMP, 'config.json'), 'w', encoding='utf-8') as f:
    json.dump({'data_dir': os.path.join(TMP, 'data'), 'rexnative_dir': os.path.join(TMP, 'rex'),
               'download_dir': DL, 'work_dir': WORK, 'work_roots': [WORK], 'own_dirs': [OWN]}, f)
os.environ['GESTOR_CONFIG'] = os.path.join(TMP, 'config.json')
sys.path.insert(0, ROOT)

from gestor import config, orders, tidy  # noqa: E402

FAILED = []


def check(what, ok):
    print('%s %s' % ('ok  ' if ok else 'FAIL', what))
    if not ok:
        FAILED.append(what)


def touch(p, n=1000, ro=False):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f:
        f.write(b'x' * n)
    if ro:
        os.chmod(p, stat.S_IREAD)


def game(slug, source, built=True):
    w = os.path.join(WORK, slug)
    touch(os.path.join(w, 'game-data', 'Default.xex'))
    with open(os.path.join(w, 'prepare.json'), 'w', encoding='utf-8') as f:
        json.dump({'source': source, 'name': slug, 'ok': True, 'steps': {}}, f)
    touch(os.path.join(w, 'archive', 'Game', 'disc1.iso'), 5000, ro=True)  # a RAR's read-only file
    touch(os.path.join(w, 'archive.part-1234', 'x.bin'))
    touch(os.path.join(w, 'src', 'game_x.cpp'))
    if built:
        touch(os.path.join(w, 'game_manifest.toml'))
        touch(os.path.join(w, 'run', 'game.exe'))
    return w


class Job:
    manager = None

    def __init__(self):
        self.events, self.result, self.params = [], {}, {}
        self._cancel = threading.Event()

    def event(self, kind, text, **kw):
        self.events.append((kind, text))

    def log(self, text):
        self.events.append(('log', text))


try:
    # A downloaded game: its archive, archive/ and a stopped run's part folder go; the rest stays.
    src = os.path.join(DL, 'item1', 'One (World).7z')
    w = game('one', src)
    touch(src, 3000)
    j = Job()
    line = tidy.after_prepare(j, w, src)
    check('the summary says so', line.startswith('; archive removed'))
    check('the downloaded archive goes', not os.path.exists(src))
    check('archive/ goes (read-only files too)', not os.path.exists(os.path.join(w, 'archive')))
    check('a part folder goes', not os.path.exists(os.path.join(w, 'archive.part-1234')))
    check('the game stays', all(os.path.exists(os.path.join(w, k)) for k in (
        'game-data/Default.xex', 'run/game.exe', 'src/game_x.cpp', 'prepare.json')))
    check('prepare no longer needs it', not tidy.prepare_needs_source(w, src))

    # Your own file is never removed; archive/ (the app's copy of it) is.
    mine = os.path.join(OWN, 'Two.7z')
    touch(mine, 3000)
    w = game('two', mine)
    tidy.after_prepare(Job(), w, mine)
    check('your own archive stays', os.path.exists(mine))
    check('its archive/ goes', not os.path.exists(os.path.join(w, 'archive')))
    check('your own file is not one to download again', tidy.download_of(mine) is None)

    # Keep downloaded archives on: nothing goes.
    src = os.path.join(DL, 'item1', 'Three.zip')
    w = game('three', src)
    touch(src)
    config.save({'keep_archives': True})
    check('keep_archives: nothing said', tidy.after_prepare(Job(), w, src) == '')
    check('keep_archives: both stay', os.path.exists(src) and os.path.isdir(os.path.join(w, 'archive')))
    config.save({'keep_archives': False})

    # Not built: nothing goes.
    src = os.path.join(DL, 'item1', 'Four.zip')
    w = game('four', src, built=False)
    touch(src)
    check('not built: nothing goes', tidy.after_prepare(Job(), w, src) == '' and os.path.exists(src))

    # An archive another job is downloading again stays.
    src = os.path.join(DL, 'item2', 'Five.rar')
    w = game('five', src)
    touch(src)

    class Busy:
        def active(self, kind=None):
            return [type('J', (), {'params': {'item': 'item2', 'name': 'Five.rar'}})()] if kind == 'download' else []

    j = Job()
    j.manager = Busy()
    tidy.after_prepare(j, w, src)
    check('an archive being downloaded stays', os.path.exists(src))

    # Prepare again: game-data or archive/ is enough; with neither, the archive is downloaded again.
    w = os.path.join(WORK, 'six')
    os.makedirs(os.path.join(w, 'game-data'))
    gone = os.path.join(DL, 'item3', 'Six (USA).7z')
    check('nothing extracted: the source is needed', tidy.prepare_needs_source(w, gone))
    check('downloaded again from its item', tidy.download_of(gone) == ('item3', 'Six (USA).7z'))
    touch(os.path.join(w, 'archive', 'Six', 'default.xex'))
    check('archive/ is enough', not tidy.prepare_needs_source(w, gone))

    # An order for a game extracted on the PC but not built, its archive gone: no download, and
    # the prepare runs in the game's own folder.
    src = os.path.join(DL, 'item4', 'Seven.rar')
    w = game('seven', src, built=False)
    tidy._rmtree(os.path.join(w, 'archive'))
    calls = []

    class Sub:
        def __init__(self, result):
            self.id, self.status, self.error, self.events, self.result = 'sub', 'ok', None, [], result
            self.progress = None

    class Manager:
        draining = False

        def active(self, kind=None, game=None):
            return []

        def get(self, i):
            return None

    class Hooks:
        manager = Manager()

        @staticmethod
        def submit_download(item, name):
            calls.append(('download', item, name))
            return Sub({})

        @staticmethod
        def submit_pipeline(title, source=None, work=None, steps=None):
            calls.append(('pipeline', source, work))
            return Sub({'work': work})

        @staticmethod
        def submit_deck(work, wait=True, root=None):
            calls.append(('deck', work))
            return Sub({})

    entry = {'item': 'item4', 'name': 'Seven.rar', 'title': 'Seven', 'slug': 'seven', 'key': 'seven',
             'size': 3000}
    orders.order_job(Job(), Hooks, entry)
    check('order: no download again', not any(c[0] == 'download' for c in calls))
    check('order: prepared in its own folder, from its recorded source',
          ('pipeline', src, w) in calls)

    # The same order with nothing extracted: the archive is downloaded first.
    shutil.rmtree(os.path.join(w, 'game-data'))
    calls.clear()
    orders.order_job(Job(), Hooks, entry)
    check('order: nothing extracted, downloaded again', calls[:1] == [('download', 'item4', 'Seven.rar')])
finally:
    def retry(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(TMP, onerror=retry)

print('\n%s' % ('ALL OK' if not FAILED else 'FAILED: %s' % ', '.join(FAILED)))
sys.exit(1 if FAILED else 0)
