"""Tests of the job queue (gestor/jobs.py) with made-up jobs: lanes side by side, a restart that
waits only for what runs, the queue coming back after it, jobs that give their turn back, one job
per game, a lane closed for a job that must run alone, per-thread settings.

    python scripts/test_jobs.py

Runs in a scratch folder (GESTOR_CONFIG points at a config made here): nothing of the app's own
data is read or written, and gestor.app is not imported (it would start the servers)."""
import json
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='gestor-test-')
with open(os.path.join(TMP, 'config.json'), 'w', encoding='utf-8') as f:
    json.dump({'data_dir': os.path.join(TMP, 'data'), 'rexnative_dir': os.path.join(TMP, 'rex')}, f)
os.environ['GESTOR_CONFIG'] = os.path.join(TMP, 'config.json')
sys.path.insert(0, ROOT)

from gestor import config, jobs, pipeline  # noqa: E402

FAILED = []


def check(what, ok):
    print('%s %s' % ('ok  ' if ok else 'FAIL', what))
    if not ok:
        FAILED.append(what)


def wait(cond, seconds=10.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


ran = []


def sleeper(name, seconds):
    def fn(job):
        ran.append(name)
        job.sleep(seconds)
        return {'done': name}
    return fn


# The recipes of this test: a job whose params say how long it sleeps can be made again.
RECIPES = {
    'slow': lambda j: sleeper(j.params['name'], j.params['seconds']) if j.params.get('seconds') else None,
    'order': lambda j: follower(j.params['follow']) if j.params.get('follow') else None,
    'wait': lambda j: waiter if j.params.get('ok') else None,
}


def follower(sub_id):
    def fn(job):
        ran.append('follow')
        m = jobs.Job.manager
        sub = m.get(sub_id)
        while sub.status in ('queued', 'running'):
            if m.draining and sub.status == 'queued' and m.resumable(sub) and m.resumable(job):
                raise jobs.Requeue()
            time.sleep(0.05)
        return {'followed': sub.status}
    return fn


def waiter(job):
    ran.append('wait')
    job.drain_stop = True
    job.sleep(60)


m = jobs.Manager()
m.resume(RECIPES)

# 1. Lanes side by side; one at a time in a lane, in order.
a = m.submit('slow', 'A', sleeper('A', 0.6), lane='build', params={'name': 'A', 'seconds': 0.6})
b = m.submit('slow', 'B', sleeper('B', 0.2), lane='build', params={'name': 'B', 'seconds': 0.2})
r = m.submit('slow', 'R', sleeper('R', 0.2), lane='report', params={'name': 'R', 'seconds': 0.2})
check('the report lane runs beside the build lane', wait(lambda: a.status == 'running' and r.status == 'running', 3))
check('the second build job waits its turn', b.status == 'queued' and (m.waiting(b) or {}).get('job') == a.id)
check('all three finish, in order in the lane', wait(lambda: all(j.status == 'ok' for j in (a, b, r))) and
      ran.index('A') < ran.index('B'))

# 2. A job cancelled while queued never runs.
a = m.submit('slow', 'A2', sleeper('A2', 0.5), lane='build', params={'name': 'A2', 'seconds': 0.5})
c = m.submit('slow', 'C2', sleeper('C2', 0.1), lane='build', params={'name': 'C2', 'seconds': 0.1})
m.cancel(c.id)
check('a queued job that is cancelled never runs', wait(lambda: a.status == 'ok') and c.status == 'cancelled' and
      'C2' not in ran)

# 3. One job per game, whatever the lane; re-entrant in a thread.
order = []


def on_game(name, seconds):
    def fn(job):
        with pipeline.game_turn(job, 'game-x'):
            with pipeline.game_turn(job, 'game-x'):
                order.append(name + ' in')
                time.sleep(seconds)
                order.append(name + ' out')
    return fn


g1 = m.submit('other', 'G1', on_game('1', 2.6), lane='build')
time.sleep(0.15)
g2 = m.submit('other', 'G2', on_game('2', 0.1), lane='report')
check('two lanes take turns on one game', wait(lambda: g1.status == 'ok' and g2.status == 'ok') and
      order == ['1 in', '1 out', '2 in', '2 out'])
check('the waiting job says what it waits for', any('Another job is working on game-x' in e['text'] for e in g2.events))

# 4. A lane closed for a job that must run alone.
r = m.submit('slow', 'R4', sleeper('R4', 0.5), lane='report', params={'name': 'R4', 'seconds': 0.5})
wait(lambda: r.status == 'running', 2)
seen = {}


def sdk(job):
    with m.alone(job, ('report',)):
        seen['report running'] = [j.title for j in m.jobs.values() if j.status == 'running' and j.lane == 'report']
        time.sleep(0.4)


s = m.submit('other', 'SDK', sdk, lane='build')
time.sleep(0.1)
r2 = m.submit('slow', 'R4b', sleeper('R4b', 0.1), lane='report', params={'name': 'R4b', 'seconds': 0.1})
check('a job that must run alone waits for the other lane and keeps it closed',
      wait(lambda: s.status == 'ok') and seen.get('report running') == [] and
      ran.index('R4') < len(ran) and wait(lambda: r2.status == 'ok') and r2.started >= s.ended)

# 5. Per-thread settings.
with config.override(rexnative_dir='X'):
    inside = config.load()['rexnative_dir'], config.get('rexnative_dir')
    other = []
    t = threading.Thread(target=lambda: other.append(config.load()['rexnative_dir']))
    t.start()
    t.join()
check('an override is this thread\'s only, and ends with the block',
      inside == ('X', 'X') and other == [os.path.join(TMP, 'rex')] and
      config.load()['rexnative_dir'] == os.path.join(TMP, 'rex') and
      config.stored()['rexnative_dir'] == os.path.join(TMP, 'rex'))

# 5b. A lane with its own copy of ReXNative: made on first use, and the job's settings point at it.
import subprocess  # noqa: E402
from gestor import rexrepo  # noqa: E402


def git(args, cwd):
    return subprocess.run(['git', '-c', 'user.name=test', '-c', 'user.email=test@example.invalid'] + args, cwd=cwd,
                          capture_output=True, text=True).returncode


origin, rex = os.path.join(TMP, 'origin'), os.path.join(TMP, 'rex')
os.makedirs(os.path.join(origin, 'rexnative'))
open(os.path.join(origin, 'rexnative', '__init__.py'), 'w').close()
git(['init', '-q', '-b', 'main'], origin)
git(['add', '-A'], origin)
git(['commit', '-q', '-m', 'first'], origin)
git(['clone', '-q', origin, rex], TMP)
git(['config', 'user.name', 'test'], rex)  # the copies share it: a cherry-pick commits
git(['config', 'user.email', 'test@example.invalid'], rex)
open(os.path.join(rex, 'ports.json'), 'w').write('{}')
check('a new game goes to the prepare lane, a build of a prepared one to the build lane',
      pipeline.pipeline_lane('some.rar') == 'prepare' and pipeline.pipeline_lane(None) == 'build')
seen = {}


def in_lane(job):
    with pipeline.lane_settings(job):
        seen[job.lane] = (config.load()['rexnative_dir'], config.get('claude_live_state'))
        time.sleep(0.4)


jp = m.submit('other', 'P', in_lane, lane='prepare')
jr = m.submit('other', 'Rp', in_lane, lane='report')
jb = m.submit('other', 'B', in_lane, lane='build')
check('prepare, report and build lanes run side by side', wait(lambda: all(j.status == 'running' for j in (jp, jr, jb)), 5))
wait(lambda: all(j.status in ('ok', 'failed') for j in (jp, jr, jb)), 20)
check('each lane with a copy works in it, and the copies were made (%s)' % (jp.error or jr.error or 'ok'),
      seen.get('prepare') == (rex + '-prepare', 'rexnative-live-manager-prepare') and
      seen.get('report') == (rex + '-reports', 'rexnative-live-manager-reports') and
      seen.get('build') == (rex, None) and
      os.path.isfile(os.path.join(rex + '-prepare', 'rexnative', '__init__.py')) and
      os.path.isfile(os.path.join(rex + '-prepare', 'ports.json')))
check('the copies know each other', sorted(os.path.basename(c) for c in rexrepo._other_copies(rex)) == ['rex-prepare', 'rex-reports'])
open(os.path.join(rex + '-prepare', 'rexnative', 'fix.py'), 'w').write('x = 1')
git(['add', 'rexnative/fix.py'], rex + '-prepare')  # not ports.json: the real repository ignores it
git(['commit', '-q', '-m', 'a fix not published'], rex + '-prepare')
said = []
rexrepo._take_unpublished(rex, lambda kind, text: said.append(text))
check('a commit not published in one copy is brought to another (%s)' % (said[:1] or ['nothing said'])[0][-90:],
      os.path.isfile(os.path.join(rex, 'rexnative', 'fix.py')))
with config.override():
    pass
cfg_off = dict(config.stored(), prepare_lane=False)
json.dump({k: v for k, v in cfg_off.items() if k in ('data_dir', 'rexnative_dir', 'prepare_lane')},
          open(os.environ['GESTOR_CONFIG'], 'w', encoding='utf-8'))
config._cache = None
check('with the prepare lane off a new game waits in the build lane', pipeline.pipeline_lane('some.rar') == 'build')
json.dump({'data_dir': cfg_off['data_dir'], 'rexnative_dir': cfg_off['rexnative_dir']},
          open(os.environ['GESTOR_CONFIG'], 'w', encoding='utf-8'))
config._cache = None

# 6. A restart: waits for what runs and for what could not continue; the rest stays queued.
del ran[:]
run1 = m.submit('slow', 'running', sleeper('running', 1.0), lane='build', params={'name': 'running', 'seconds': 1.0})
wait(lambda: run1.status == 'running', 2)
later = m.submit('slow', 'later', sleeper('later', 0.1), lane='build', params={'name': 'later', 'seconds': 0.1})
norecipe = m.submit('other', 'no recipe', sleeper('norecipe', 0.2), lane='build')
foll = m.submit('order', 'follows later', follower(later.id), lane='orders', params={'follow': later.id})
wt = m.submit('wait', 'only waits', waiter, lane='deck', params={'ok': True})
wait(lambda: foll.status == 'running' and wt.status == 'running', 2)
t0 = time.time()
check('a restart is not ready while a job runs', m.drain() is False)
first, after = m.drain_state()
check('it says what it waits for and what continues',
      {j.title for j in first} == {'running', 'no recipe'} and
      {j.title for j in after} == {'later', 'follows later', 'only waits'})
check('a queued job that continues afterwards says so', (m.waiting(later) or {}).get('restart') is True)
check('the restart is ready once the running jobs end', wait(m.drain, 10))
took = time.time() - t0
check('it waited for the running job and the one without a recipe, not for the queue (%.1f s)' % took,
      run1.status == 'ok' and norecipe.status == 'ok' and later.status == 'queued' and 'later' not in ran and
      1.0 <= took < 6)
check('the follower and the waiting job gave their turn back',
      foll.status == 'queued' and wt.status == 'queued' and foll.ended is None)
new = m.submit('slow', 'after stop', sleeper('after stop', 0.1), lane='build', params={'name': 'after stop', 'seconds': 0.1})
time.sleep(1.3)
check('nothing starts once the app is about to close', new.status == 'queued')
m.save()

# 7. The app opens again: the queue is back, in order; a job without a recipe is interrupted.
del ran[:]
saved = json.load(open(m.path, encoding='utf-8'))
for d in saved:  # as if a job of an older version, with nothing saved, had been queued
    if d['title'] == 'after stop':
        d['params'] = {}
json.dump(saved, open(m.path, 'w', encoding='utf-8'))
m2 = jobs.Manager()
check('before the recipes are known the queued jobs wait as interrupted', m2.get(later.id).status == 'interrupted')
n = m2.resume(RECIPES)
check('3 jobs are back in the queue (%d)' % n, n == 3)
check('the queue runs after the restart', wait(lambda: m2.get(later.id).status == 'ok' and
                                                 m2.get(foll.id).status == 'ok', 10))
check('the follower followed the job it had', m2.get(foll.id).result.get('followed') == 'ok')
check('a job that saved too little stays interrupted', m2.get(new.id).status == 'interrupted')
check('the waiting job runs again', wait(lambda: m2.get(wt.id).status == 'running', 3))
m2.cancel(wt.id)
check('and can be cancelled', wait(lambda: m2.get(wt.id).status == 'cancelled', 5))
check('finished jobs keep their state', m2.get(run1.id).status == 'ok')

print()
print('FAILED: %s' % ', '.join(FAILED) if FAILED else 'all passed')
sys.exit(1 if FAILED else 0)
