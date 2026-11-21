"""Preparar, compilar e testar um jogo, com o Claude a corrigir o que falha.

Passos (cada um com o seu registo em <data_dir>/logs/<tarefa>-<passo>-<n>.log):
  prepare  python -m rexnative prepare <arquivo> --work <work_dir> --title-update --dlc --project ...
  build    python -m rexnative project <work> --build            (um jogo já preparado)
  boot     scripts/live.ps1 start/frame/status/stop: o jogo tem de desenhar boot_min_frames frames
           (linhas "ReXNative: frames N | per frame: draws ...") sem relatório de crash.
Um passo que falha vai ao Claude (claude.py) até claude_max_attempts vezes; depois de cada
correção o passo corre outra vez (antes de repetir o teste de arranque, o jogo é compilado de novo
se o Claude mudou alguma coisa)."""
import ctypes
import glob
import json
import os
import re
import shutil
import subprocess
import time

from . import catalog, claude, config, games, jobs, rexrepo, state, xna

FRAME_LINE = re.compile(r'ReXNative: frames (\d+) \| per frame: draws ([\d.]+).*?frame ([\d.]+) ms')
CRASH = re.compile(r'crash report, rexglue|==== end of crash report|\bFATAL\b|access violation',
                   re.I)
# ReXNative d91d88e: a fault in the native path no longer kills the game; it hands it to the classic
# renderer at the next Swap and logs this line.
NATIVE_FAULT = re.compile(r'ReXNative: the native path read a bad guest address in (\S+)')
STEP_TITLE = {'prepare': 'Prepare', 'build': 'Build', 'boot': 'Boot test on the PC',
              'compare': 'Compare native and classic', 'deckpc': 'Test with the Deck settings',
              'selftest': 'Self-test', 'scenes': 'Test scenes'}


def _rex(cfg):
    return [config.python_exe(), '-u', '-m', 'rexnative']


def _step_log(job, step, attempt):
    return os.path.join(config.data_dir('logs'), '%s-%s-%d.log' % (job.id, step, attempt))


def _fail(step, summary, **kw):
    return dict(step=step, summary=summary, **kw)


def free_gb(path):
    p = path
    while p and not os.path.exists(p):
        p = os.path.dirname(p)
    return shutil.disk_usage(p or '.').free / 1e9


# -- prepare / build --------------------------------------------------------------------------
def step_prepare(job, ctx, attempt):
    cfg = config.load()
    src = ctx['source']
    need = os.path.getsize(src) * 2.5 / 1e9 if os.path.exists(src) else 0
    if not os.path.isdir(os.path.join(ctx['work'], 'game-data')) and free_gb(cfg['work_dir']) < need:
        return False, _fail('prepare', 'Not enough free space on %s: %.1f GB free, ~%.0f GB '
                            'needed' % (cfg['work_dir'], free_gb(cfg['work_dir']), need),
                            no_fix=True)
    log = _step_log(job, 'prepare', attempt)
    cmd = _rex(cfg) + ['prepare', src, '--work', cfg['work_dir']] + list(cfg['prepare_args'])
    rc = job.run(cmd, cwd=cfg['rexnative_dir'], env=config.tool_env(), log_path=log)
    prep = games._read_json(os.path.join(ctx['work'], 'prepare.json'))
    if rc == 0 and prep.get('ok'):
        return True, {'summary': 'prepared and built'}
    why = prep.get('error') or 'exit code %d' % rc
    return False, _fail('prepare', 'Preparation failed: %s' % why[:300], command=_cmdline(cmd),
                        cwd=cfg['rexnative_dir'], rc=rc, log_path=log, tail=jobs.tail(log, 220),
                        details='prepare.json error: %s\n' % prep.get('error') if prep.get('error') else '')


def step_build(job, ctx, attempt):
    cfg = config.load()
    log = _step_log(job, 'build', attempt)
    cmd = _rex(cfg) + ['project', ctx['work'], '--build']
    rc = job.run(cmd, cwd=cfg['rexnative_dir'], env=config.tool_env(), log_path=log)
    if rc == 0 and games.exe_name(ctx['work']) and \
            os.path.exists(os.path.join(ctx['work'], 'run', games.exe_name(ctx['work']) + '.exe')):
        return True, {'summary': 'built'}
    return False, _fail('build', 'The build failed (code %d)' % rc, command=_cmdline(cmd),
                        cwd=cfg['rexnative_dir'], rc=rc, log_path=log, tail=jobs.tail(log, 220))


def _cmdline(cmd):
    return ' '.join('"%s"' % c if ' ' in str(c) else str(c) for c in cmd)


# -- teste de arranque (scripts/live.ps1) --------------------------------------------------------
def _live(args, timeout=90, state_dir=None):
    cfg = config.load()
    script = os.path.join(cfg['rexnative_dir'], 'scripts', 'live.ps1')
    env = config.tool_env()
    if state_dir:
        env['REXNATIVE_LIVE_STATE'] = state_dir
    r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script]
                       + [str(a) for a in args], capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=timeout, env=env,
                       creationflags=jobs.CREATE_NO_WINDOW)
    return r.returncode, (r.stdout + r.stderr).strip()


def _live_state(state_dir=None):
    p = os.path.join(state_dir or os.path.join(os.environ.get('LOCALAPPDATA', ''), 'rexnative-live'), 'state.json')
    try:
        return json.load(open(p, encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None


def pid_alive(pid):
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


def _live_running(state_dir=None):
    s = _live_state(state_dir)
    if not s or not pid_alive(s.get('pid', 0)):
        return None
    # O state.json fica para trás quando o jogo fecha: um PID reaproveitado por outro programa não
    # é o jogo (live.ps1 também compara o caminho).
    if s.get('exe') and not s.get('renderdoc'):
        try:
            import psutil
            exe = psutil.Process(int(s['pid'])).exe()
            if os.path.basename(exe).lower() != os.path.basename(s['exe']).lower():
                return None
        except Exception:  # noqa: BLE001 - sem acesso ao processo: fica como estava
            pass
    return s


def stop_leftover_live(job, work):
    """Uma sessão do Claude pode deixar aberto o jogo que arrancou com live.ps1 (e cancelá-la não
    o fecha): o jogo ao vivo desta pasta fecha-se, para não ocupar os testes seguintes. Na pasta de
    estado das sessões do assistente (claude.live_state_dir) e na de origem."""
    from . import claude
    for state_dir in (claude.live_state_dir(), None):
        s = _live_running(state_dir)
        if not s or not s.get('dir'):
            continue
        d, w = os.path.normcase(os.path.abspath(s['dir'])), os.path.normcase(os.path.abspath(work))
        if d == w or d.startswith(w + os.sep):
            try:
                _live(['stop', '-Dir', s['dir']], timeout=60, state_dir=state_dir)
                job.event('info', 'Closed the game Claude left running (%s)' % os.path.basename(s.get('exe') or ''))
            except (subprocess.SubprocessError, OSError) as e:
                job.log('could not close the live game: %s' % e)


def _game_log(run, since):
    cands = glob.glob(os.path.join(run, 'logs', 'live', 'live.log*')) + \
        glob.glob(os.path.join(run, 'live', 'live.log*'))
    cands = [c for c in cands if os.path.getmtime(c) >= since - 2]
    return max(cands, key=os.path.getmtime) if cands else None


def _log_sizes(run):
    """O tamanho de cada live.log* antes de um arranque: o ReXGlue pode continuar a escrever no
    mesmo ficheiro, e só o que vem depois é deste arranque."""
    out = {}
    for c in glob.glob(os.path.join(run, 'logs', 'live', 'live.log*')) +             glob.glob(os.path.join(run, 'live', 'live.log*')):
        out[os.path.normcase(c)] = os.path.getsize(c)
    return out


class LogReader:
    """parse_log aos bocados: a cada volta só lê o que o registo cresceu (o live.log de um jogo
    junta todos os arranques e chega às centenas de MB; o que vem depois de offsets é deste)."""

    def __init__(self, offsets=None):
        self.offsets = offsets or {}
        self.path = None
        self.pos = 0
        self.rest = b''
        self.frames_max = 0
        self.last = None
        self.crash = []
        self.report_lines = None
        self.fault = None
        self.errors = 0

    def read(self, path):
        if path and path != self.path:
            self.__init__(self.offsets)
            self.path = path
            self.pos = self.offsets.get(os.path.normcase(path), 0)
        if self.path:
            try:
                with open(self.path, 'rb') as f:
                    f.seek(self.pos)
                    data = f.read()
                self.pos += len(data)
            except OSError:
                data = b''
            data = self.rest + data
            cut = data.rfind(b'\n')
            chunk, self.rest = (data[:cut + 1], data[cut + 1:]) if cut >= 0 else (b'', data)
            self._take(chunk.decode('utf-8', 'replace'))
        return self.result()

    def _take(self, text):
        for m in FRAME_LINE.finditer(text):
            self.frames_max = max(self.frames_max, int(m.group(1)))
            self.last = m.groups()
        for l in text.splitlines():
            if self.report_lines is not None and len(self.report_lines) < 80:
                self.report_lines.append(l)
            if CRASH.search(l) and len(self.crash) < 5:
                self.crash.append(l)
            if 'crash report' in l and self.report_lines is None:
                self.report_lines = [l]
            if self.fault is None and NATIVE_FAULT.search(l):
                self.fault = l.strip()
            if '[error]' in l or ' E ' in l[:40]:
                self.errors += 1

    def result(self):
        last = self.last
        return {'frames': self.frames_max,
                'draws': float(last[1]) if last else 0.0, 'frame_ms': float(last[2]) if last else 0.0,
                'crash': list(self.crash), 'crash_report': '\n'.join(self.report_lines or []),
                'native_fault': self.fault, 'errors': self.errors}


def _classic_now(job, run, live_dir, out_dir, t):
    """O interruptor do renderizador (o F9 do jogo) passa ao clássico, a mesma imagem tirada dele, e
    volta ao nativo. Devolve o caminho da captura do clássico, ou None."""
    wait = float(config.load().get('compare_switch_wait') or 1.5)
    try:
        _control(run, 'renderer stock')
        time.sleep(wait)
        src = capture_frame(live_dir)
        if not src:
            job.log('classic capture at %d s: no picture' % t)
            return None
        dst = os.path.join(out_dir, 'pairc-%03d.png' % t)
        shutil.copyfile(src, dst)
        return dst
    except OSError as e:
        job.log('classic capture at %d s failed: %s' % (t, e))
        return None
    finally:
        try:
            _control(run, 'renderer native')
            time.sleep(0.5)
        except OSError:
            pass


def parse_log(path, offsets=None):
    text = ''
    if path:
        with open(path, 'rb') as f:
            f.seek((offsets or {}).get(os.path.normcase(path), 0))
            text = f.read().decode('utf-8', 'replace')
    frames = FRAME_LINE.findall(text)
    lines = text.splitlines()
    crash = [l for l in lines if CRASH.search(l)]
    report = ''
    if any('crash report' in l for l in lines):
        i = next(i for i, l in enumerate(lines) if 'crash report' in l)
        report = '\n'.join(lines[i:i + 80])
    last = frames[-1] if frames else None
    fault = next((l.strip() for l in lines if NATIVE_FAULT.search(l)), None)
    return {'frames': max((int(f[0]) for f in frames), default=0),
            'draws': float(last[1]) if last else 0.0, 'frame_ms': float(last[2]) if last else 0.0,
            'crash': crash[:5], 'crash_report': report, 'native_fault': fault,
            'errors': sum(1 for l in lines if '[error]' in l or ' E ' in l[:40])}


def _stock(work, name):
    """O jogo arranca com o ReXNative desligado ([rexnative] enabled = false no run/<nome>.toml):
    desenha o renderizador do ReXGlue, que não escreve as linhas "ReXNative: frames"."""
    import tomllib
    try:
        with open(os.path.join(work, 'run', name + '.toml'), encoding='utf-8') as f:
            t = tomllib.loads(f.read())
    except (OSError, ValueError):
        return False
    return (t.get('rexnative') or {}).get('enabled') is False


def set_classic(work, name, on=True):
    """O jogo arranca no renderizador clássico (ou no nativo, on=False), no PC e no Deck: a chave que a
    opção Renderer do HUD escreve, em run/<nome>.toml e deck.toml."""
    for path in (os.path.join(work, 'run', name + '.toml'), os.path.join(work, 'deck.toml')):
        games.write_text(path, games.apply_values(games.read_text(path), {'rexnative.classic': on}))


def classic_fallback(job, ctx, why):
    """The native renderer did not get through the boot test and no fix came: the same boot test
    on ReXGlue's classic renderer (Xenia's). If the game runs there, it starts on it from now on (on
    the PC and on the Deck: [rexnative] classic = true, the key the HUD's Renderer option writes;
    the HUD still switches to the native one) and the pipeline goes on instead of failing."""
    cfg = config.load()
    work = ctx['work']
    name = games.exe_name(work)
    if not cfg.get('classic_fallback', True) or not name:
        return False
    g = games.info(work)
    if (g.get('classic') or {}).get('pc'):
        return False  # it already ran on the classic renderer
    job.event('step', 'The native renderer did not get through (%s): trying the classic renderer '
                      '(Xenia\'s) instead of failing' % why[:200])
    if not wait_live_free(job):
        return False
    run = os.path.join(work, 'run')
    res = timed_run(job, ctx['slug'], run, name, 'classic', boot=True)
    # Builds before ReXNative d91d88e print no frame lines on the classic renderer: then pictures
    # that are not one plain colour stand for frames.
    pictures = [c for c in res.get('captures') or [] if os.path.exists(c['path']) and not suspicious(c['path'])]
    enough = res.get('frames', 0) >= cfg['boot_min_frames'] or (not res.get('frames') and len(pictures) >= 2)
    if not (res.get('running') and not res.get('crash') and enough):
        job.event('fail', 'The classic renderer did not get through either (%s, %d frames)' % (
            'running' if res.get('running') else 'not running', res.get('frames') or 0))
        return False
    set_classic(work, name)
    shot = None
    if res.get('captures'):
        shot = os.path.join(config.data_dir('shots'), ctx['slug'] + '.png')
        try:
            shutil.copyfile(res['captures'][-1]['path'], shot)
        except OSError:
            shot = None
    state.update('games', state.game_key(work), {'boot': dict(
        {k: res.get(k) for k in ('frames', 'draws', 'frame_ms', 'crash', 'errors', 'running', 'seconds', 'log',
                                 'captures')}, at=jobs.now(), ok=True, shot=shot, classic_fallback=True,
        native_error=why[:500])})
    job.event('ok', 'Runs on the classic renderer: %d frames in %d s. It starts on it on the PC and the '
                    'Deck from now on (the HUD, View + Menu, switches to the native one)' % (
                        res.get('frames') or 0, res.get('seconds') or 0))
    ctx['classic_fallback'] = True
    return True


def step_boot(job, ctx, attempt):
    cfg = config.load()
    work = ctx['work']
    name = games.exe_name(work)
    run = os.path.join(work, 'run')
    exe = os.path.join(run, (name or '?') + '.exe')
    if not name or not os.path.exists(exe):
        return False, _fail('boot', 'No executable in %s: build it first' % run,
                            command='-', cwd=run, rc=-1, log_path='', tail='', no_fix=False)
    if not wait_live_free(job):
        return False, _fail('boot', 'The PC is still testing another game (live.ps1): try again '
                            'later', no_fix=True)
    pair = bool(cfg.get('compare_enabled', True) and cfg.get('compare_one_run', True) and
                'compare' in (ctx.get('steps') or []) and not _stock(work, name) and
                not (games.info(work).get('classic') or {}).get('pc'))
    from . import scenes
    want_scene = not _stock(work, name) and not (games.info(work).get('classic') or {}).get('pc') and \
        not any(m.get('source') == 'boot' and not m.get('stale') for m in scenes.scenes(ctx['slug']))
    res = timed_run(job, ctx['slug'], run, name, 'native', boot=True, pair_classic=pair, record=want_scene)
    if res.get('scene_trace'):
        try:
            if res.get('running') and not res.get('crash') and not res.get('native_fault'):
                scenes.add(work, ctx['slug'], res['scene_trace'], 'boot',
                           'Where the boot test ends (%d s)' % (res.get('seconds') or 0))
                job.event('info', 'A test scene of where the boot test ends was recorded (its reference '
                                  'pictures come in the Test scenes step)')
            else:
                os.remove(res['scene_trace'])
        except OSError as e:
            job.log('boot scene not kept: %s' % e)
        res.pop('scene_trace', None)
    # As capturas do nativo mudaram: a comparação que havia é de antes (fica marcada).
    cmp = state.get('games', state.game_key(work), {}).get('compare')
    if cmp and not cmp.get('stale'):
        cmp['stale'] = True
        state.update('games', state.game_key(work), {'compare': cmp})
    if res.get('start_error'):
        return False, _fail('boot', 'live.ps1 start failed: %s' % res['start_error'][-300:],
                            command='live.ps1 start', cwd=run, rc=1, log_path='', tail=res['start_error'])
    gl = res['log']
    shot = None
    if res['captures']:  # a última captura é a do teste (a que a app mostra)
        shot = os.path.join(config.data_dir('shots'), '%s.png' % ctx['slug'])
        shutil.copyfile(res['captures'][-1]['path'], shot)
    res['shot'] = shot
    res['at'] = jobs.now()
    res['suspicious'] = suspicious(shot) if shot else None
    res['rex'] = (rexrepo.status() or {}).get('head')
    stock = _stock(work, name)
    ok = res['running'] and not res['crash'] and (res['frames'] >= cfg['boot_min_frames'] or stock)
    if ok and res.get('native_fault') and not (games.info(work).get('classic') or {}).get('pc'):
        # The game runs, but on the classic renderer: the native path faulted and ReXNative handed
        # it over. It starts on the classic one from now on, and Claude is asked to fix the native
        # path (the report, after the pipeline).
        set_classic(work, name)
        res['classic_fallback'] = True
        res['native_error'] = res['native_fault'][:500]
        ctx['native_handover'] = res['native_fault']
        job.event('info', 'The native path faulted and ReXNative handed the game to the classic renderer: '
                          'it starts on the classic one from now on (%s)' % res['native_fault'][-200:])
    if ok and stock and res['frames'] < cfg['boot_min_frames']:
        res['stock'] = True
        state.update('games', state.game_key(work), {'boot': dict(
            {k: res.get(k) for k in ('frames', 'draws', 'frame_ms', 'crash', 'errors', 'running', 'seconds', 'log')},
            at=jobs.now(), ok=True, stock=True, captures=[])})
        return True, {'summary': 'running after %d s, no crash (ReXNative is off for this game: '
                                 'the ReXGlue renderer does not count frames)' % res['seconds']}
    res['ok'] = ok
    state.update('games', state.game_key(work), {'boot': res})
    if ok:
        if res['suspicious']:
            job.event('info', 'It started, but the capture of the last frame is almost all one colour '
                      '(%s): there may be graphics errors. Check it in the game and, if it looks wrong, '
                      'use "Report a problem".' % res['suspicious'])
        return True, {'summary': '%d frames in %d s, %.0f draws, %.1f ms per frame' % (
            res['frames'], res['seconds'], res['draws'], res['frame_ms'])}
    if res['crash']:
        why = 'crash: %s' % res['crash'][0][-200:]
    elif not res['running']:
        why = 'the game closed after %d s' % res['seconds']
    elif not res['frames']:
        why = 'running but no frame statistics after %d s' % res['seconds']
    else:
        why = 'only %d frames in %d s (minimum %d)' % (res['frames'], res['seconds'], cfg['boot_min_frames'])
    details = ('Boot test result: running=%s, frames=%d, draws/frame=%.1f, frame %.1f ms, '
               '%d seconds, crash lines: %s\n' % (res['running'], res['frames'], res['draws'],
                                                  res['frame_ms'], res['seconds'], res['crash'][:3]))
    if res['crash_report']:
        details += 'Crash report from the game log:\n```\n%s\n```\n' % res['crash_report']
    if shot:
        details += 'A capture of the last frame (you can look at it): %s\n' % shot
    details += ('The boot test starts the game with `scripts\\live.ps1 start -Dir "%s" -Exe %s.exe`'
                ' (1280x720 window); success = still running after %d s with at least %d frames in '
                'the "ReXNative: frames N | per frame: draws ..." log lines and no crash report.\n'
                % (run, name, cfg['boot_seconds'], cfg['boot_min_frames']))
    return False, _fail('boot', 'The boot test failed: %s' % why, command='live.ps1 start',
                        cwd=run, rc=0, log_path=gl or '', tail=jobs.tail(gl, 200) if gl else '(no log)',
                        details=details)


def step_scenes(job, ctx, attempt):
    """As cenas de teste do jogo desenhadas por esta compilação contra as suas referências (os
    mesmos frames: só o renderizador muda). Nunca falha o pipeline: o resultado fica no estado do
    jogo (scenes_check) e o lote de suspeitos decide com ele."""
    from . import scenes
    work, slug = ctx['work'], ctx['slug']
    if not scenes.scenes(slug):
        return True, {'summary': 'none yet (record one while playing: Play on this PC, then Save this scene)'}
    name = games.exe_name(work)
    if _stock(work, name) or (games.info(work).get('classic') or {}).get('pc'):
        return True, {'summary': 'skipped: the game runs on the classic renderer'}
    r = scenes.check_all(job, work, slug)
    out = {'at': jobs.now(), 'rex': scenes.build_rex(work), 'checked': r['checked'], 'worse': r['worse'],
           'better': r['better'], 'changed': r['changed'], 'job': job.id}
    state.update('games', state.game_key(work), {'scenes_check': out})
    ctx['scenes'] = out
    if not r['checked']:
        return True, {'summary': 'reference pictures made; nothing to compare yet'}
    same = r['checked'] - len(r['worse']) - len(r['better']) - len(r['changed'])
    return True, {'summary': '%d checked: %d same%s%s%s' % (
        r['checked'], same, ', %d better' % len(r['better']) if r['better'] else '',
        ', %d changed (look at them)' % len(r['changed']) if r['changed'] else '',
        ', %d WORSE' % len(r['worse']) if r['worse'] else '')}


def step_selftest(job, ctx, attempt):
    """O autoteste do ciclo com o Claude: passa quando estado.txt diz "ok"."""
    path = os.path.join(ctx['work'], 'estado.txt')
    text = open(path, encoding='utf-8').read().strip() if os.path.exists(path) else ''
    job.log('self-test: estado.txt = %r' % text)
    if text == 'ok':
        return True, {'summary': 'estado.txt says ok'}
    return False, _fail('selftest', 'The self-test failed on purpose: estado.txt says %r' % text,
                        command='(the app reads estado.txt)', cwd=ctx['work'], rc=1, log_path=job.log_path,
                        tail='self-test: %s must contain exactly the word ok, it contains %r' % (path, text),
                        selftest=True)


def wait_live_free(job):
    """live.ps1 guarda UM jogo de cada vez: o de outra pessoa nunca é fechado (-Force não).
    Espera até 10 minutos; False se continuar ocupado."""
    for i in range(120):
        other = _live_running()
        if not other:
            return True
        if i == 0:
            job.event('info', 'Another game is being tested on the PC (%s): waiting for it to finish'
                      % other.get('exe'))
        job.sleep(5)
    return False


def compare_dir(slug):
    return config.data_dir('compare', slug)


def capture_frame(live_dir, timeout=10.0):
    """A captura do próprio renderizador da imagem seguinte: o pedido <live>/cap/capture.request e o
    f<imagem>-native.png que ele escreve (o que `live.ps1 frame` faz, sem lançar um PowerShell por
    captura). Devolve o caminho, quando o ficheiro deixa de crescer, ou None."""
    cap = os.path.join(live_dir, 'cap')
    os.makedirs(cap, exist_ok=True)
    before = time.time()
    with open(os.path.join(cap, 'capture.request'), 'w'):
        pass
    found = None
    while not found and time.time() - before < timeout:
        time.sleep(0.2)
        cands = []
        for p in glob.glob(os.path.join(cap, 'f*-native.png')):
            try:
                if os.path.getmtime(p) >= before:
                    cands.append(p)
            except OSError:
                pass
        found = max(cands, key=os.path.getmtime) if cands else None
    if not found:
        return None
    last = -1
    for _ in range(50):
        time.sleep(0.3)
        try:
            n = os.path.getsize(found)
        except OSError:
            return None
        if n > 0 and n == last:
            break
        last = n
    return found


def _control(run, line):
    """Um comando para o renderizador (<run>/live/control.txt, lido e apagado a cada imagem)."""
    with open(os.path.join(run, 'live', 'control.txt'), 'a', encoding='ascii') as f:
        f.write(line + '\n')


def timed_run(job, slug, run, name, mode, boot=False, flags='', pair_classic=False, record=False):
    """Arranca o jogo com live.ps1 (mode 'native' ou 'classic', o renderizador do ReXGlue) e
    tira capturas do próprio renderizador aos compare_times segundos (as mesmas nas duas
    execuções, para as comparar). boot: também vê se arranca (frames, crash) e pode esperar até
    boot_seconds_max por estatísticas. pair_classic: a seguir a cada captura do nativo, o
    interruptor do renderizador (renderer stock) passa ao clássico, tira-se a mesma imagem do
    clássico e volta ao nativo: o mesmo momento nos dois (pair_classic na resposta). Devolve
    parse_log + running, seconds, log, captures."""
    cfg = config.load()
    times = sorted(int(t) for t in cfg.get('compare_times') or [15, 30, 45, 60])
    extra = '--rexnative_capture_xenos=false'  # só a imagem do renderizador, nos dois modos
    if mode == 'classic':
        extra += ' --rexnative_classic=true'
    if flags:
        extra += ' ' + flags
    out_dir = compare_dir(slug)
    for f in os.listdir(out_dir):
        if f.startswith(mode + '-') or (pair_classic and f.startswith('pairc-')):
            os.remove(os.path.join(out_dir, f))
    offsets = _log_sizes(run)
    t0 = time.time()
    try:
        rc, out = _live(['start', '-Dir', run, '-Exe', name + '.exe', '-Extra', extra])
    except (subprocess.SubprocessError, OSError) as e:
        # O live.ps1 não respondeu: se o jogo chegou a arrancar, fecha-se.
        rc, out = 1, 'live.ps1 start did not answer: %s' % e
        s = _live_running()
        if s and os.path.normcase(os.path.abspath(s.get('dir') or '')) == os.path.normcase(os.path.abspath(run)):
            try:
                _live(['stop', '-Dir', run], timeout=60)
            except (subprocess.SubprocessError, OSError):
                pass
    job.log(out)
    if rc != 0:
        return {'start_error': out, 'captures': [], 'log': None, 'running': False, 'frames': 0}
    mine = (_live_state() or {}).get('pid')
    caps, res, gl = [], {}, None
    pairs = []
    live_dir = os.path.join(run, 'live')
    reader = LogReader(offsets)
    pending = list(times)
    route = parse_route(cfg.get('compare_route') or '')
    control = os.path.join(run, 'live', 'control.txt')
    end = max(times[-1] + 3, cfg['boot_seconds'] if boot else 0)
    try:
        while True:
            soon = [x for x in ([pending[0]] if pending else []) + ([route[0][0]] if route else [])]
            job.sleep(1 if soon and min(soon) - (time.time() - t0) < 5 else 5)
            el = time.time() - t0
            # Os botões da rota (START, A...) no comando do jogo, pelo ficheiro de controlo do
            # renderizador (como live.ps1 pad:): os mesmos segundos nas duas execuções, para
            # passar do ecrã de título ao jogo.
            while route and el >= route[0][0]:
                _, buttons, ms = route.pop(0)
                try:
                    with open(control, 'a', encoding='ascii') as f:
                        f.write('pad %s %d\n' % (buttons, ms))
                    job.log('pad %s at %.0f s' % (buttons, el))
                except OSError as e:
                    job.log('pad %s not sent: %s' % (buttons, e))
            alive = bool(mine) and pid_alive(mine)
            gl = _game_log(run, t0)
            res = reader.read(gl)
            if res['crash'] or not alive:
                break
            if pending and el >= pending[0]:
                t = pending.pop(0)
                src = capture_frame(live_dir)
                if src:
                    dst = os.path.join(out_dir, '%s-%03d.png' % (mode, t))
                    shutil.copyfile(src, dst)
                    caps.append({'t': t, 'path': dst})
                    if pair_classic:
                        pc = _classic_now(job, run, live_dir, out_dir, t)
                        if pc:
                            pairs.append({'t': t, 'path': pc})
                else:
                    job.log('capture at %d s failed: no picture from the renderer in 10 s' % t)
            if el >= end and not pending:
                if not boot or res['frames'] >= cfg['boot_min_frames']:
                    if record:
                        # A cena de teste do arranque: os frames a que o teste chega, uma vez por jogo.
                        from . import scenes
                        try:
                            res['scene_trace'] = scenes.record_live(run)
                        except (scenes.SceneError, OSError) as e:
                            job.log('no boot scene: %s' % e)
                    break
            if el >= (cfg['boot_seconds_max'] if boot else end + 30):
                break
        res['running'] = bool(mine) and pid_alive(mine)
        res['seconds'] = round(time.time() - t0)
        if pair_classic:
            res['pair_classic'] = pairs
    finally:
        s = _live_state()
        if s and mine and s.get('pid') == mine:
            _live(['stop'], timeout=60)
    res['log'] = gl
    res['captures'] = caps
    return res


def parse_route(text):
    """'18:START,21:A' -> [(18.0, 'START', 200), (21.0, 'A', 200)] ("seg:botões[:ms]"; botões A B X
    Y START BACK UP DOWN LEFT RIGHT LB RB, juntos com +)."""
    out = []
    for item in (text or '').split(','):
        parts = item.strip().split(':')
        if len(parts) >= 2 and parts[1]:
            try:
                out.append((float(parts[0]), parts[1].strip().upper(),
                            int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 200))
            except ValueError:
                pass
    return sorted(out)


COMPARE_SCHEMA = {
    'type': 'object',
    'properties': {
        'verdict': {'type': 'string', 'enum': ['iguais', 'nativo_com_erros', 'brilho_diferente',
                                                'classico_com_erros', 'cenas_diferentes', 'inconclusivo']},
        'pairs': {'type': 'array', 'items': {'type': 'object', 'properties': {
            't': {'type': 'integer'}, 'native_ok': {'type': 'boolean'}, 'note': {'type': 'string'}},
            'required': ['t', 'native_ok', 'note']}},
        'summary': {'type': 'string'},
    },
    'required': ['verdict', 'pairs', 'summary'],
}

COMPARE_PROMPT = """Compare two renderers of the Xbox 360 game "{title}". Read the image {sheet}: each
row is one moment after the game started ({times} seconds); on the LEFT the frame drawn by
ReXNative's native renderer, on the RIGHT the frame drawn by ReXGlue's Xenos renderer (Xenia's,
the reference) in a second run at the same time.

In both runs the same pad buttons were pressed at the same seconds ({route}) to get from the
title screen into the game, so later rows usually show menus or gameplay.
The two runs are separate starts of the game: a small offset is normal, and many games pick a
random intro or attract sequence, so a row may show two DIFFERENT screens. For each row:
1. Decide whether both pictures show the same screen (same content, maybe a little earlier or later).
2. Same screen: native_ok = false if the native one is missing things the reference has (geometry,
   textures, text, HUD, particles), has clearly wrong colours, or shows garbage. A difference ONLY
   in overall brightness, contrast, gamma, fog density or post-processing (bloom, blur, depth of
   field, vignette, grain) is not a fault: the reference may be the wrong one there (keep
   native_ok = true and describe the difference).
3. Different screens: judge the native picture ON ITS OWN and set native_ok = false only for
   unmistakable rendering faults: a blank white, black or grey screen with almost nothing on it,
   huge stretched triangles or wedges, smeared trails of earlier frames, random garbage. Deliberate
   styles are NOT faults: retro or 8-bit looks, striped loading borders, pixel fonts, scanlines,
   fades, plain loading screens.
   Intro logos often ANIMATE: they assemble from or break into pixels or blocks, dissolve, fade in
   or out (the background darkening too). When one picture shows such a logo mid-animation and the
   other shows it whole, it is the same screen at another moment (the native renderer is usually
   faster, so a little ahead): native_ok = true, "cenas_diferentes" if nothing else differs.
In each note say first "same screen" or "different screens", then what is wrong (or "right").
Verdict: "iguais" (the native looks right everywhere), "nativo_com_erros" (a clear fault in at least
one native picture: something missing, garbage, a blank screen), "brilho_diferente" (same content,
only brightness / contrast / gamma / fog / post-processing differ: the user decides in the game
which one is right), "classico_com_erros" (the reference is the broken one), "cenas_diferentes" (the
screens differ and nothing in the native ones is clearly wrong) or "inconclusivo".
summary: one or two short sentences in English for the user."""

ONE_RUN_NOTE = """

NOTE: here both pictures of each row come from the SAME run: the native frame, then the renderer
switch to the reference and its frame about a second and a half later. The screens are the same
unless the game moved on in that second and a half (a cut, a fade, a menu that opened): judge them
as the same screen."""


def _pair_diff(a, b):
    """Diferença média (0-100) entre as duas imagens reduzidas: só uma pista."""
    from PIL import Image, ImageChops, ImageStat
    x = Image.open(a).convert('RGB').resize((96, 54))
    y = Image.open(b).convert('RGB').resize((96, 54))
    d = ImageStat.Stat(ImageChops.difference(x, y)).mean
    return round(sum(d) / 3 / 2.55, 1)


def _compare_sheet(pairs, path, keys=('native', 'classic'),
                   label='native (left)   |   Xenos reference (right)'):
    from PIL import Image, ImageDraw, ImageFont
    w, h = 640, 360
    img = Image.new('RGB', (w * 2 + 30, len(pairs) * (h + 40) + 10), (24, 24, 24))
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arialbd.ttf', 26)
    except OSError:
        font = ImageFont.load_default()
    for i, pr in enumerate(pairs):
        y = 10 + i * (h + 40)
        dr.text((10, y), '%d s   %s' % (pr['t'], label), fill=(255, 220, 0), font=font)
        for j, key in enumerate(keys):
            im = Image.open(pr[key]).convert('RGB')
            im.thumbnail((w, h))
            img.paste(im, (10 + j * (w + 10), y + 34))
    img.save(path, quality=88)


def step_compare(job, ctx, attempt):
    """O mesmo jogo com o renderizador clássico (o do ReXGlue), capturas nos mesmos tempos que o
    teste de arranque, e a comparação (diferença das imagens e o modelo barato a vê-las). Não
    falha o pipeline: marca o jogo e deixa os pares para um relatório."""
    cfg = config.load()
    work = ctx['work']
    name = games.exe_name(work)
    run = os.path.join(work, 'run')
    key = state.game_key(work)
    boot = state.get('games', key, {}).get('boot') or {}
    natives = {c['t']: c['path'] for c in boot.get('captures') or [] if os.path.exists(c['path'])}
    if not natives:
        job.event('info', 'No native captures to compare (the boot test did not take any)')
        return True, {'summary': 'nothing to compare'}
    same = {c['t']: c['path'] for c in boot.get('pair_classic') or [] if os.path.exists(c['path'])}
    usable = [t for t in same if t in natives]
    # Os pares do teste de arranque (o mesmo momento): servem se houver pelo menos metade e se o
    # clássico não for todo de uma cor onde o nativo tem imagem (o interruptor não pegou).
    blank = [t for t in usable if suspicious(same[t]) and not suspicious(natives[t])]
    if len(usable) >= max(1, len(natives) // 2) and len(blank) < len(usable):
        one_run = True
        res = {'running': True, 'frames': boot.get('frames')}
        classics = same
        job.event('info', 'Classic captures from the boot test itself (the renderer switch, the same '
                          'moments): no second run')
    else:
        one_run = False
        if usable:
            job.event('info', 'The classic captures of the boot test are not usable (%d of %d blank): '
                              'a second run on the classic renderer' % (len(blank), len(usable)))
        if not wait_live_free(job):
            job.event('info', 'The PC is still testing another game: comparison postponed')
            return True, {'summary': 'postponed'}
        res = timed_run(job, ctx['slug'], run, name, 'classic')
        classics = {c['t']: c['path'] for c in res.get('captures') or []}
    pairs = [{'t': t, 'native': natives[t], 'classic': classics[t],
              'diff': _pair_diff(natives[t], classics[t])} for t in sorted(natives) if t in classics]
    out = {'at': jobs.now(), 'pairs': pairs, 'classic_running': res.get('running'),
           'classic_frames': res.get('frames'), 'one_run': one_run}
    if not pairs:
        out.update(verdict='inconclusivo', summary='The classic renderer gave no captures (%s).' % (
            'it closed' if not res.get('running') else 'no frames'))
    else:
        sheet = os.path.join(compare_dir(ctx['slug']), 'comparacao.jpg')
        _compare_sheet(pairs, sheet)
        out['sheet'] = sheet
        try:
            prompt = COMPARE_PROMPT.format(
                title=games.info(work)['title'], sheet=os.path.basename(sheet),
                times=', '.join(str(p['t']) for p in pairs),
                route=cfg.get('compare_route') or 'none')
            if one_run:
                prompt += ONE_RUN_NOTE
            answer, cost = claude.ask(prompt, COMPARE_SCHEMA, cwd=compare_dir(ctx['slug']))
            notes = {int(x.get('t', -1)): x for x in answer.get('pairs') or []}
            for pr in pairs:
                n = notes.get(pr['t'])
                if n:
                    pr['native_ok'] = bool(n.get('native_ok'))
                    pr['note'] = n.get('note')
            out.update(verdict=answer.get('verdict'), summary=answer.get('summary'), cost=cost)
        except Exception as e:  # noqa: BLE001 - sem o Claude fica a diferença das imagens
            worst = max(p['diff'] for p in pairs)
            out.update(verdict='inconclusivo', summary='No opinion from the model (%s); largest '
                       'difference between the images %.0f%%.' % (e, worst))
    state.update('games', key, {'compare': out})
    text = {'iguais': 'Native same as classic', 'nativo_com_erros': 'THE NATIVE RENDERER HAS GRAPHICS ERRORS',
            'brilho_diferente': 'Different brightness or contrast (check in the game which one is right)',
            'classico_com_erros': 'The classic one is wrong', 'cenas_diferentes': 'Different moments',
            'inconclusivo': 'Inconclusive'}.get(out['verdict'], out['verdict'])
    job.event('ok' if out['verdict'] == 'iguais' else 'info', '%s: %s' % (text, out.get('summary') or ''),
              cost=out.get('cost'))
    if out['verdict'] == 'nativo_com_erros':
        ctx['native_faults'] = out
    return True, {'summary': text}


# -- o jogo no PC com as definições do Deck -----------------------------------------------------------
# O Deck usa outras definições (1280x800, o upscaler ligado, FSR): há erros que só aparecem com
# elas (o Tetris Splash desenhava só a metade esquerda com o upscaler). O mesmo arranque, com as
# definições que o Deck vai usar passadas na linha de comandos (--secção.nome=valor), capturas nos
# mesmos segundos e o modelo barato a comparar com as do teste de arranque.
DECK_SCHEMA = {
    'type': 'object',
    'properties': {
        'verdict': {'type': 'string', 'enum': ['iguais', 'deck_com_erros', 'cenas_diferentes', 'inconclusivo']},
        'summary': {'type': 'string'},
        'pairs': {'type': 'array', 'items': {'type': 'object', 'properties': {
            't': {'type': 'integer'}, 'deck_ok': {'type': 'boolean'}, 'note': {'type': 'string'}},
            'required': ['t', 'deck_ok']}},
    },
    'required': ['verdict', 'summary'],
}

DECK_PROMPT = """Compare the Xbox 360 game "{title}" drawn by the same renderer with two settings. Read the
image {sheet}: each row is one moment after the game started ({times} seconds); on the LEFT the PC's
settings (a 1280x720 window, no upscaler), on the RIGHT the Steam Deck's settings (1280x800 and the
FSR upscaler on), run on the same PC; both runs pressed the same buttons at the same seconds
({route}).

Is the RIGHT one broken where the LEFT is right? Broken: part of the screen missing or black (for
example only one half drawn), blocks of garbage or noise, wrong colours, things see-through or
missing, a black frame where the left has a picture.
Not broken: the other size or aspect (1280x800), a softer or sharper picture, small brightness
differences, the game being at a slightly different moment.
Share of each frame that is black on the right but not on the left (by row): {dark}

verdict: "iguais" (the right is fine in every row), "deck_com_erros" (the right is broken in at least
one row), "cenas_diferentes" (the rows show different moments, so you cannot tell), "inconclusivo".
summary: one or two sentences in English.
pairs: for each row, t (seconds), deck_ok (the right is fine) and a short note in English."""


def deck_flags(work):
    """As definições que o Deck vai usar (rexnative.deck.package: as do kit para o Deck com as do
    jogo, deck.toml, por cima) como opções da linha de comandos, sem o ecrã inteiro e com o FSR
    (no PC o upscaler escolheria o DLSS)."""
    import tomllib
    name, _ = games.rexnative('deck').package(work)
    path = os.path.join(work, 'deck', name + '-deck.toml')
    data = tomllib.loads(open(path, encoding='utf-8').read())
    flags = []
    for section, kv in data.items():
        if section not in ('ui', 'rexnative') or not isinstance(kv, dict):
            continue
        for k, v in kv.items():
            if section == 'ui' and k == 'fullscreen':
                continue
            if isinstance(v, bool):
                v = 'true' if v else 'false'
            v = str(v)
            if ' ' in v or '"' in v:
                continue
            flags.append('--%s.%s=%s' % (section, k, v))
    if (data.get('rexnative') or {}).get('upscaler') and 'upscaler_backend' not in (data.get('rexnative') or {}):
        flags.append('--rexnative.upscaler_backend=fsr')
    return ' '.join(flags)


def _dark_extra(a, b):
    """A parte da imagem b que é preta onde a imagem a não é (grelha de 32x18)."""
    try:
        from PIL import Image
        ia = Image.open(a).convert('L').resize((32, 18))
        ib = Image.open(b).convert('L').resize((32, 18))
    except Exception:  # noqa: BLE001
        return 0.0
    pa, pb = list(ia.getdata()), list(ib.getdata())
    return sum(1 for x, y in zip(pa, pb) if y < 12 and x > 30) / len(pa)


def step_deckpc(job, ctx, attempt):
    """O jogo no PC com as definições do Deck, comparado com o teste de arranque. Não falha o
    pipeline: marca o jogo e, com erros, manda-os ao Claude como um problema do Deck."""
    cfg = config.load()
    work = ctx['work']
    name = games.exe_name(work)
    run = os.path.join(work, 'run')
    key = state.game_key(work)
    boot = state.get('games', key, {}).get('boot') or {}
    natives = {c['t']: c['path'] for c in boot.get('captures') or [] if os.path.exists(c['path'])}
    if not natives:
        job.event('info', 'No boot test captures to compare')
        return True, {'summary': 'nothing to compare'}
    try:
        flags = deck_flags(work)
    except Exception as e:  # noqa: BLE001
        job.event('info', 'Could not read the Deck settings: %s' % e)
        return True, {'summary': 'no Deck settings'}
    if not wait_live_free(job):
        job.event('info', 'The PC is still testing another game: Deck test postponed')
        return True, {'summary': 'postponed'}
    job.log('Deck settings: %s' % flags)
    res = timed_run(job, ctx['slug'], run, name, 'deck', flags=flags)
    decks = {c['t']: c['path'] for c in res.get('captures') or []}
    pairs = [{'t': t, 'native': natives[t], 'deck': decks[t], 'dark': round(_dark_extra(natives[t], decks[t]), 3)}
             for t in sorted(natives) if t in decks]
    out = {'at': jobs.now(), 'pairs': pairs, 'flags': flags, 'running': res.get('running'),
           'frames': res.get('frames')}
    if not pairs:
        out.update(verdict='deck_com_erros' if not res.get('running') else 'inconclusivo',
                   summary='With the Deck settings the game %s.' % (
                       'closed before the captures' if not res.get('running') else 'gave no captures'))
    else:
        sheet = os.path.join(compare_dir(ctx['slug']), 'deck-pc.jpg')
        _compare_sheet(pairs, sheet, keys=('native', 'deck'),
                       label='PC settings (left)   |   Deck settings (right)')
        out['sheet'] = sheet
        dark = ', '.join('%d s: %.0f%%' % (p['t'], 100 * p['dark']) for p in pairs)
        try:
            answer, cost = claude.ask(DECK_PROMPT.format(
                title=games.info(work)['title'], sheet=os.path.basename(sheet),
                times=', '.join(str(p['t']) for p in pairs), route=cfg.get('compare_route') or 'none',
                dark=dark), DECK_SCHEMA, cwd=compare_dir(ctx['slug']))
            notes = {int(x.get('t', -1)): x for x in answer.get('pairs') or []}
            for pr in pairs:
                n = notes.get(pr['t'])
                if n:
                    pr['deck_ok'] = bool(n.get('deck_ok'))
                    pr['note'] = n.get('note')
            out.update(verdict=answer.get('verdict'), summary=answer.get('summary'), cost=cost)
        except Exception as e:  # noqa: BLE001 - sem o modelo, a parte preta a mais
            worst = max(p['dark'] for p in pairs)
            out.update(verdict='deck_com_erros' if worst > 0.2 else 'inconclusivo',
                       summary='No opinion from the model (%s); with the Deck settings up to %.0f%% of '
                               'the picture is black where it is not on the PC.' % (e, 100 * worst))
    state.update('games', key, {'deckpc': out})
    text = {'iguais': 'Same with the Deck settings', 'deck_com_erros': 'ERRORS WITH THE DECK SETTINGS',
            'cenas_diferentes': 'Different moments', 'inconclusivo': 'Inconclusive'}.get(out['verdict'], out['verdict'])
    job.event('ok' if out['verdict'] == 'iguais' else 'info', '%s: %s' % (text, out.get('summary') or ''),
              cost=out.get('cost'))
    if out['verdict'] == 'deck_com_erros':
        ctx['deck_faults'] = out
    return True, {'summary': text}


def _auto_report(job, work, slug, label, kind_where, text, caps, said):
    """Guarda um relatório automático e põe na fila a tarefa que o manda ao Claude (modelo forte).
    label: o que vai no título da tarefa; kind_where: (tipo, onde); said: o aviso na tarefa atual."""
    rid = '%s-%s' % (slug, jobs.now().replace(':', '').replace('-', ''))
    state.update('reports', rid, {'work': state.game_key(work), 'slug': slug, 'at': jobs.now(),
                                  'kind': kind_where[0], 'where': kind_where[1],
                                  'text': text, 'captures': caps, 'status': 'queued', 'auto': True})
    if SUBMIT is None:
        job.event('info', 'Automatic report saved (%s), but there is no queue to send it to Claude' % rid)
        return rid
    title = games.info(work)['title']
    j2 = SUBMIT('report', 'Automatic report%s: %s' % (label, title), lambda j: report_job(j, work, rid),
                'build', slug, {'report': rid, 'auto': True})
    state.update('reports', rid, {'job': j2.id})
    job.event('info', said, job=j2.id)
    return rid


def auto_report_handover(job, work, slug, line):
    """A report for a native path that faulted (ReXNative handed the game to the classic renderer):
    Claude tries to fix the native path; the game meanwhile starts on the classic one."""
    text = ('Automatic report: during the boot test the native path faulted and ReXNative handed the '
            'game to the classic renderer at the next Swap: "%s". The game now starts on the classic '
            'renderer ([rexnative] classic = true in run/<name>.toml and deck.toml). Fix the native path '
            '(gated to this game or its D3D version if it is risky for the others); when the native '
            'renderer draws it right, set classic back to false in both files.' % line[:400])
    return _auto_report(job, work, slug, ' (native fault)', ('Graphics on the native renderer', 'PC'), text,
                        [], 'Claude is asked to fix the native path, in the next job')


def auto_report_deck(job, work, slug, out):
    """Um relatório do teste com as definições do Deck (as capturas lado a lado), ao Claude."""
    caps = [p for pr in out.get('pairs') or [] for p in (pr['native'], pr['deck'])]
    if out.get('sheet'):
        caps.append(out['sheet'])
    notes = ''.join('\n- %d s: %s' % (pr['t'], pr.get('note') or '') for pr in out.get('pairs') or []
                    if pr.get('deck_ok') is False)
    text = ('Automatic report: on the PC, with the Steam Deck settings (%s), the game has errors it '
            'does not have with the PC settings. %s%s\nThe captures come in pairs (PC settings, Deck '
            'settings, at the same seconds). Reproduce it with those options (live.ps1 start -Extra "...").' % (
                out.get('flags'), out.get('summary') or '', notes))
    return _auto_report(job, work, slug, ' (Deck)', ('Graphics on the native renderer', 'Steam Deck'), text,
                        caps, 'Errors with the Deck settings: Claude asked to investigate them in the next job')


def suspicious(png):
    """Uma descrição curta se a captura é quase toda de uma só cor (um frame branco ou preto com
    pouco por cima, como o nativo a falhar), senão None. Um ecrã de carregamento também pode
    ser assim: é só um aviso."""
    try:
        from PIL import Image
        im = Image.open(png).convert('RGB').resize((160, 90))
    except Exception:  # noqa: BLE001
        return None
    q = [(r >> 4, g >> 4, b >> 4) for r, g, b in im.getdata()]
    from collections import Counter
    (color, n), = Counter(q).most_common(1)
    share = n / len(q)
    if share < 0.85:
        return None
    lum = sum(color) * 16 / 3
    if lum < 30:  # preto: transições, carregamentos e cenas escuras também o são
        return None
    what = 'white' if lum > 220 else 'one colour'
    return '%d%% %s' % (round(share * 100), what)


STEPS = {'prepare': step_prepare, 'build': step_build, 'boot': step_boot, 'compare': step_compare,
         'deckpc': step_deckpc, 'scenes': step_scenes}
TEST_STEPS = {'selftest': step_selftest}


def selftest(job):
    """Prova o ciclo: um passo que falha numa pasta à parte, o Claude corrige, o passo passa."""
    d = config.data_dir('selftest')
    with open(os.path.join(d, 'estado.txt'), 'w', encoding='utf-8') as f:
        f.write('broken\n')
    # Corre na pista rápida, ao lado das compilações: não atualiza a worktree do ReXNative.
    job.result['synced'] = True
    return run(job, work=d, steps=['selftest'])


# -- o pipeline --------------------------------------------------------------------------------
def run(job, source=None, work=None, steps=None, auto_report=True, fallback=True):
    """source: um arquivo descarregado (jogo novo: prepare); work: um jogo já preparado (build).
    steps: os passos a correr (por omissão prepare+boot ou build+boot). fallback: o renderizador
    clássico quando o nativo não passa (não nos testes de suspeitos nem nos relatórios, onde
    esconderia o que a mudança estragou)."""
    cfg = config.load()
    tests = ['boot', 'scenes'] + (['compare'] if cfg.get('compare_enabled', True) else []) + (
        ['deckpc'] if cfg.get('deck_test_enabled', True) else [])
    if source:
        slug = catalog.slug(source)
        work = os.path.join(cfg['work_dir'], slug)
        steps = steps or ['prepare'] + tests
    else:
        work = os.path.abspath(work)
        slug = os.path.basename(work)
        steps = steps or ['build'] + tests
    ctx = {'source': source, 'work': work, 'slug': slug}
    if (source and xna.is_xna_name(source)) or xna.is_xna_work(work):
        job.event('fail', xna.UNSUPPORTED_PT)
        state.update('games', state.game_key(work), {'pipeline': {'job': job.id, 'status': 'failed',
                                                                  'at': jobs.now(), 'error': 'XNA'}})
        raise RuntimeError(xna.UNSUPPORTED_PT)
    if not job.result.get('synced'):
        rexrepo.sync(job)
        job.result['synced'] = True
    title = job.title
    history = []
    fixes = job.result.setdefault('claude', [])
    key = state.game_key(work)
    state.update('games', key, {'pipeline': {'job': job.id, 'status': 'running', 'at': jobs.now()}})
    done = []
    # O progresso com pormenor (progress.py): o passo, a tentativa e quando começou.
    from . import progress
    job.progress = lambda: progress.pipeline(job, work)
    job.result['steps_all'] = list(steps)
    try:
        i = 0
        attempts = 0
        while i < len(steps):
            step = steps[i]
            ctx['steps'] = steps
            job.check()
            if step == 'scenes' and (ctx.get('native_handover') or ctx.get('classic_fallback')):
                job.event('info', 'Test scenes skipped: the game runs on the classic renderer', step=step)
                done.append(step)
                i += 1
                continue
            if step == 'compare' and (ctx.get('native_handover') or ctx.get('classic_fallback') or
                                      (games.info(work).get('classic') or {}).get('pc')):
                # O jogo arranca no clássico: as duas execuções seriam do clássico.
                job.event('info', 'Compare skipped: the game runs on the classic renderer', step=step)
                done.append(step)
                i += 1
                continue
            job.event('step', '%s%s' % (STEP_TITLE.get(step, step), ' (again)' if step in done else ''), step=step)
            job.result.update(step=step, attempt=attempts + 1, step_t0=time.time(), steps_done=list(done))
            ok, info = (STEPS.get(step) or TEST_STEPS[step])(job, ctx, attempts + 1)
            if ok:
                job.event('ok', '%s: %s' % (STEP_TITLE.get(step, step), info['summary']), step=step)
                done.append(step)
                i += 1
                continue
            job.event('fail', info['summary'], step=step)
            if xna.is_xna_work(work):
                job.event('fail', xna.UNSUPPORTED_PT)
                raise RuntimeError(xna.UNSUPPORTED_PT)
            def use_classic(msg):
                # A boot test that failed for good: the classic renderer, if the game runs there.
                return fallback and step == 'boot' and not info.get('no_fix') and classic_fallback(job, ctx, msg)
            if info.get('no_fix') or not cfg['claude_enabled'] or attempts >= cfg['claude_max_attempts']:
                if use_classic(info['summary']):
                    done.append(step)
                    steps = steps[:i + 1] + [s for s in steps[i + 1:] if s != 'compare']
                    i += 1
                    continue
                raise RuntimeError(info['summary'])
            attempts += 1
            info.update(title=title, slug=slug, work=work)
            for k in ('command', 'cwd', 'rc', 'log_path', 'tail', 'details'):
                info.setdefault(k, '')
            job.result.update(step='claude', step_t0=time.time())
            try:
                fx = claude.fix(job, info, attempts, '\n'.join(history))
            finally:
                stop_leftover_live(job, work)
            fixes.append(dict(step=step, attempt=attempts, **{k: fx.get(k) for k in (
                'summary', 'commits', 'pushed', 'edited', 'cost', 'gave_up', 'rex_note', 'suspects')}))
            history.append('- attempt %d on step %s: %s' % (attempts, step, fx['summary'][:1500]))
            if fx['gave_up'] or not fx['ok']:
                msg = ('Claude found no fix: %s' % fx['summary'][:500]) if fx['gave_up'] else fx['summary']
                if use_classic(msg):
                    done.append(step)
                    steps = steps[:i + 1] + [s for s in steps[i + 1:] if s != 'compare']
                    i += 1
                    continue
                raise RuntimeError(msg)
            # Depois de uma correção, o teste de arranque corre sobre um jogo compilado de novo.
            if step == 'boot' and (fx['commits'] or fx['edited']) and 'build' not in steps[i:i + 1]:
                steps = steps[:i] + ['build'] + steps[i:]
        # Um jogo novo fica já com arte para o Steam (o modelo barato escolhe a capa oficial); sem
        # capas o pipeline não falha.
        if source and not os.path.exists(os.path.join(work, 'deck', 'art', 'portrait.png')):
            job.event('step', 'Covers for Steam (the cheap model picks them)')
            try:
                from . import covers
                r = covers.auto_pick(work, log=lambda s: job.event('info', s))
                job.event('ok', 'Covers: %s' % ', '.join(r['art']), cost=r.get('cost'))
            except Exception as e:  # noqa: BLE001
                job.event('info', 'No automatic covers: %s (pick them in the Covers tab)' % e)
        if auto_report:  # dentro de um relatório, o balanço é o do relatório (report_job)
            contrib_event(job, fixes)
            share_contribution(job, fixes, work, slug)
            if not job.result.get('batch_child'):
                queue_suspects(job, fixes, slug)
        # A comparação viu falhas no nativo: um relatório automático ao Claude (modelo forte), numa
        # tarefa a seguir (a não ser que esta já seja a de um relatório).
        if auto_report and ctx.get('native_faults') and cfg['claude_enabled'] and \
                cfg.get('compare_auto_report', True):
            rid = auto_report_faults(job, work, slug, ctx['native_faults'])
            job.result['auto_report'] = rid
        elif auto_report and ctx.get('native_handover') and cfg['claude_enabled'] and \
                cfg.get('compare_auto_report', True):
            rid = auto_report_handover(job, work, slug, ctx['native_handover'])
            job.result['auto_report'] = rid
        elif auto_report and ctx.get('deck_faults') and cfg['claude_enabled'] and \
                cfg.get('compare_auto_report', True):
            rid = auto_report_deck(job, work, slug, ctx['deck_faults'])
            job.result['auto_report'] = rid
        state.update('games', key, {'pipeline': {'job': job.id, 'status': 'ok', 'at': jobs.now(),
                                                 'fixes': len(fixes)}})
        return {'work': work, 'slug': slug}
    except jobs.Cancelled:
        state.update('games', key, {'pipeline': {'job': job.id, 'status': 'cancelled', 'at': jobs.now()}})
        raise
    except Exception as e:
        if fixes and auto_report:
            contrib_event(job, fixes)
            if not job.result.get('batch_child'):
                try:
                    queue_suspects(job, fixes, slug)
                except Exception:  # noqa: BLE001
                    pass
        state.update('games', key, {'pipeline': {'job': job.id, 'status': 'failed', 'at': jobs.now(),
                                                 'error': str(e)[:500], 'fixes': len(fixes)}})
        raise


# -- relatórios do utilizador ----------------------------------------------------------------------
def report_job(job, work, report_id):
    """O Claude (modelo forte) investiga o relatório; se mudou alguma coisa, o jogo é compilado e
    testado outra vez (com o ciclo de correção, se a compilação falhar)."""
    rep = state.get('reports', report_id) or {}
    state.update('reports', report_id, {'status': 'investigating', 'job': job.id})
    rexrepo.sync(job)
    job.result['synced'] = True
    try:
        fx = claude.investigate(job, work, rep)
    except jobs.Cancelled:
        state.update('reports', report_id, {'status': 'cancelled'})
        raise
    finally:
        stop_leftover_live(job, work)
    job.result.setdefault('claude', []).append(dict(step='report', attempt=1, **{k: fx.get(k) for k in (
        'summary', 'commits', 'pushed', 'edited', 'cost', 'gave_up', 'rex_note', 'suspects')}))
    state.update('reports', report_id, {'summary': fx['summary'], 'commits': fx['commits'],
                                        'edited': fx['edited'], 'pushed': fx['pushed'],
                                        'rex_note': fx.get('rex_note')})
    kept = keep_report_scenes(job, work, rep, report_id, fx.get('summary') or '')
    if not fx['ok']:
        state.update('reports', report_id, {'status': 'failed'})
        raise RuntimeError(fx['summary'])
    if fx['commits'] or fx['edited']:
        try:
            run(job, work=work, steps=['build', 'boot', 'scenes', 'compare'] if config.load().get('compare_enabled', True)
                else ['build', 'boot', 'scenes'], auto_report=False, fallback=False)
        except jobs.Cancelled:
            state.update('reports', report_id, {'status': 'cancelled'})
            raise
        except Exception as e:
            state.update('reports', report_id, {'status': 'failed: the fix did not pass the tests (%s)' % str(e)[:200]})
            contrib_event(job, job.result.get('claude') or [])
            queue_suspects(job, job.result.get('claude') or [], rep.get('slug'))
            raise
    elif kept:
        # Sem compilação nova: as imagens de referência da cena são as desta compilação.
        from . import scenes
        for sid in kept:
            try:
                scenes.make_refs(job, work, rep.get('slug') or os.path.basename(work), sid)
            except scenes.SceneError as e:
                job.event('info', 'Scene of the report: %s' % e)
    status = 'no fix' if fx['gave_up'] else ('fixed: check it in the game' if (
        fx['commits'] or fx['edited']) else 'investigated')
    state.update('reports', report_id, {'status': status})
    job.event('ok', 'Report: %s' % status)
    contrib_event(job, job.result.get('claude') or [])
    share_contribution(job, job.result.get('claude') or [], work, rep.get('slug') or os.path.basename(work))
    queue_suspects(job, job.result.get('claude') or [], rep.get('slug'))
    return {'report': report_id}


def keep_report_scenes(job, work, rep, report_id, summary):
    """As cenas que o Claude gravou no sítio do relatório (linhas "SCENE: <trace.rxt>" no fim da
    resposta) passam a cenas de teste do jogo: depois de cada mudança no ReXNative, esse sítio é
    desenhado outra vez e comparado. Devolve os ids."""
    from . import scenes
    slug = rep.get('slug') or os.path.basename(work)
    run_dir = os.path.normcase(os.path.abspath(os.path.join(work, 'run')))
    kept = []
    for path in claude.parse_scenes(summary):
        p = os.path.abspath(path.strip().strip('`"'))
        if not p.lower().endswith('.rxt') or not os.path.isfile(p) or \
                not os.path.normcase(p).startswith(run_dir):
            job.event('info', 'Scene of the report not kept (not a trace of this game): %s' % path[:200])
            continue
        label = 'Report: %s' % (rep.get('text') or '').split(';')[0][:80]
        meta = scenes.add(work, slug, p, 'report', label, report=report_id)
        kept.append(meta['id'])
        job.event('ok', 'Kept the scene of the report as a test scene: %s' % label)
    if kept:
        state.update('reports', report_id, {'scenes': kept})
    return kept


def queue_suspects(job, fixes, own_slug):
    """Se as correções desta tarefa deixaram commits no ReXNative, testa (numa tarefa a seguir)
    os outros jogos que o Claude apontou como suspeitos de passar pelo código mudado."""
    cfg = config.load()
    commits = [c for f in fixes for c in f.get('commits') or []]
    suspects = []
    for f in fixes:
        for x in f.get('suspects') or []:
            w = games.find(x) if x != own_slug and x not in suspects else None
            if w and not xna.is_xna_work(w):  # um XNA nunca corre: não diz nada da mudança
                suspects.append(x)
    if not commits or not cfg.get('test_suspects_after_fix', True):
        return None
    if not suspects:
        job.event('info', 'Claude named no other games that go through the changed code: '
                  'no follow-up test')
        return None
    if SUBMIT is None:
        return None
    reason = ('Suspects of %s (Claude named them because they go through the changed code): %s' % (
        ', '.join(c.split(' ', 1)[0] for c in commits), ', '.join(suspects)))
    j2 = SUBMIT('batch', 'Test %d suspect(s) of the fix' % len(suspects),
                lambda j: batch_job(j, suspects, reason), 'build', None,
                {'slugs': suspects, 'reason': reason})
    job.event('info', 'Testing the suspect games (%s) in the next job' % ', '.join(suspects), job=j2.id)
    return j2.id


def share_contribution(job, fixes, work, slug):
    """Quem não pode publicar no ReXNative (todos menos quem o mantém): os commits do assistente que
    ficaram por publicar vão num pull request para o ReXNative, com o que ele encontrou e os testes
    (github.share_fix). Quem pode publicar já o fez (o assistente faz push para o main)."""
    commits = []
    for f in fixes:
        if f.get('pushed'):
            continue
        for c in f.get('commits') or []:
            if c not in commits:
                commits.append(c)
    if not commits:
        return None
    from . import github
    if github.status().get('can_push'):
        return None
    g = state.get('games', state.game_key(work), {}) or {}
    boot, cmp = g.get('boot') or {}, g.get('compare') or {}
    tests = []
    if boot:
        tests.append('- Boot test: %s, %s frames in %s s%s' % (
            'runs' if boot.get('ok') else 'FAILS', boot.get('frames'), boot.get('seconds'),
            (', %.1f ms per frame' % boot['frame_ms']) if boot.get('frame_ms') else ''))
    if cmp.get('verdict'):
        tests.append('- Native vs classic: %s' % cmp['verdict'])
    summary = '\n\n'.join((f.get('summary') or '').strip() for f in fixes if f.get('commits'))
    try:
        return github.share_fix(job, config.load()['rexnative_dir'], slug, games.info(work)['title'], commits,
                                summary, '\n'.join(tests))
    except Exception as e:  # noqa: BLE001 - partilhar não pode fazer falhar o jogo
        job.event('info', 'The fix was not shared: %s' % str(e)[:200])
        return None


def contrib_event(job, fixes):
    """No fim da tarefa: o que levou ao ReXNative (commits e o que mudou para todos os jogos)."""
    commits, notes = [], []
    for f in fixes:
        for c in f.get('commits') or []:
            if c not in commits:
                commits.append(c)
        if f.get('rex_note'):
            notes.append(f['rex_note'])
    if commits:
        job.event('ok', 'Contribution to ReXNative: %d commit(s)%s\n%s' % (
            len(commits), (' — ' + ' '.join(notes)) if notes else '', '\n'.join(commits)))
    else:
        job.event('info', 'No changes to ReXNative%s' % (
            ' (only in the game folder)' if any(f.get('edited') for f in fixes) else ''))


# Quem põe as tarefas em fila (app.py liga-o ao gestor de tarefas): submit(kind, title, fn, lane, game, params).
SUBMIT = None


def auto_report_faults(job, work, slug, cmp):
    """Um relatório com o que a comparação viu e os pares de capturas, e a tarefa que o manda ao
    Claude. Devolve o id do relatório."""
    caps = [p for pr in cmp.get('pairs') or [] for p in (pr['native'], pr['classic'])]
    notes = ''.join('\n- %d s: %s' % (pr['t'], pr.get('note') or '') for pr in cmp.get('pairs') or []
                    if pr.get('native_ok') is False)
    how = 'in the same run, through the renderer switch' if cmp.get('one_run') else 'in two runs'
    text = ('Automatic report from the native / classic comparison (the same seconds after the '
            'start, %s): %s%s\nFirst confirm, with the game open and the classic renderer '
            'alongside, that it really is an error of the native renderer; if the native one is right '
            '(or the reference is wrong), say so and change nothing.' % (how, cmp.get('summary') or '', notes))
    return _auto_report(job, work, slug, '', ('Graphics on the native renderer', 'PC'), text, caps,
                        'The native renderer has errors: Claude (strong model) asked to investigate them '
                        'in the next job')


# -- testar vários jogos (os suspeitos de uma mudança) ----------------------------------------------


def batch_job(job, slugs, reason=''):
    """Compila, testa e compara cada jogo, um de cada vez, e diz qual piorou (o arranque falhou,
    ou a comparação passou a ver erros no nativo). Sem relatórios automáticos: o resultado vem no
    fim, para decidir."""
    if reason:
        job.event('info', reason)
    job.result['batch_child'] = True
    rows = []
    for slug in slugs:
        job.check()
        w = games.find(slug)
        if not w:
            rows.append((slug, slug, 'not found', False))
            continue
        if xna.is_xna_work(w):
            job.event('info', '%s is left out: it is XNA (does not run for now)' % slug)
            continue
        title = games.info(w)['title']
        key = state.game_key(w)
        job.event('step', 'Testing %s (%d of %d)' % (title, len(rows) + 1, len(slugs)), game=slug)
        try:
            # Compila, arranca e desenha as cenas de teste do jogo com a compilação nova: os mesmos
            # frames que a referência, por isso uma diferença é da mudança. As capturas aos 15/30/45/60
            # s (intros, transições) já não decidem: um arranque mais lento dava "pior" sem nada pior.
            state.update('games', key, {'scenes_check': None})
            run(job, work=w, steps=['build', 'boot', 'scenes'], auto_report=False, fallback=False)
            g = state.get('games', key, {})
            boot_ok = (g.get('boot') or {}).get('ok') and not (g.get('boot') or {}).get('classic_fallback')
            sc = g.get('scenes_check') or {}
            worse = (not boot_ok) or bool(sc.get('worse'))
            if not sc.get('checked'):
                scene_text = 'no test scenes to compare yet'
            else:
                same = sc['checked'] - len(sc.get('worse') or []) - len(sc.get('better') or []) - len(sc.get('changed') or [])
                scene_text = 'scenes: %d same%s%s%s' % (
                    same, ', %d better' % len(sc['better']) if sc.get('better') else '',
                    ', %d changed (look at them)' % len(sc['changed']) if sc.get('changed') else '',
                    ', WORSE: %s' % ', '.join(sc['worse']) if sc.get('worse') else '')
            text = '%s; %s' % ('boots' if boot_ok else 'DOES NOT BOOT', scene_text)
            rows.append((slug, title, text, worse))
            job.event('fail' if worse else 'ok', '%s: %s' % (title, text), game=slug)
        except jobs.Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 - um jogo que falha não pára os outros
            rows.append((slug, title, 'failed: %s' % str(e)[:200], True))
            job.event('fail', '%s: failed: %s' % (title, str(e)[:300]), game=slug)
    bad = [r for r in rows if r[3]]
    job.event('fail' if bad else 'ok', ('%d of %d got worse: %s' % (len(bad), len(rows), ', '.join(r[1] for r in bad)))
              if bad else 'None of the %d games got worse' % len(rows))
    job.result['batch'] = [{'slug': r[0], 'title': r[1], 'result': r[2], 'worse': r[3]} for r in rows]
    if bad:
        raise RuntimeError('%d game(s) got worse: %s' % (len(bad), ', '.join(r[1] for r in bad)))
    return {'tested': len(rows)}
