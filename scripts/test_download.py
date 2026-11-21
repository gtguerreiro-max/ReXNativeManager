"""Tests of the download worker (gestor/worker.py) with a made-up connection: a line that drops
now and then still finishes a large file; five drops in a row that bring nothing end it.

    python scripts/test_download.py"""
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gestor import worker  # noqa: E402

FAILED = []


def check(what, ok):
    print('%s %s' % ('ok  ' if ok else 'FAIL', what))
    if not ok:
        FAILED.append(what)


class File:
    exists = True


sys.modules['internetarchive'] = types.SimpleNamespace(
    get_item=lambda item: types.SimpleNamespace(get_file=lambda name: File()))
worker.time.sleep = lambda s: None
MB = 1 << 20


def run(plan, size):
    """plan: what each connection brings before it drops (bytes), None = to the end."""
    dest = os.path.join(tempfile.mkdtemp(prefix='gestor-dl-'), 'file.bin')
    calls = []

    def fetch(f, dest, size, state):
        step = plan[len(calls)] if len(calls) < len(plan) else None
        calls.append(step)
        have = os.path.getsize(dest) if os.path.exists(dest) else 0
        with open(dest, 'ab') as out:
            out.write(b'\0' * (size - have if step is None else step))
        if step is not None:
            raise ConnectionError('dropped')
    worker.fetch = fetch
    try:
        worker.download('item', 'name', dest, size, '')
        return 'done', len(calls)
    except SystemExit as e:
        return str(e), len(calls)


out = run([20 * MB] * 9, 200 * MB)
check('nine drops that each brought 20 MB still finish the file (%s, %d connections)' % out, out == ('done', 10))
out = run([0, 0, 0, 0, 0, 0, 0], 50 * MB)
check('five drops in a row that bring nothing end it (%d connections)' % out[1], out[0] != 'done' and out[1] == 5)
out = run([0, 0, 0, 0, 20 * MB, 0, 0, 0, 0, None], 50 * MB)
check('progress starts the count again (%s, %d connections)' % out, out == ('done', 10))
print()
print('FAILED: %s' % ', '.join(FAILED) if FAILED else 'all passed')
sys.exit(1 if FAILED else 0)
