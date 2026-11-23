"""Correção automática com o Claude Code em modo não interativo (`claude -p`).

Quando um passo do pipeline falha, a app dá ao Claude o passo, o comando, o fim do registo e as
regras do ReXNative; o Claude corrige o ReXNative (na worktree das builds, faz commit e push) ou a
pasta do jogo, e a app volta a correr o passo. A saída vem em stream-json: cada texto e cada
ferramenta que o Claude usa aparecem na tarefa enquanto ele trabalha.

O Claude Code corre com a sessão da linha de comandos (`claude auth login`, uma vez) ou com
CLAUDE_CODE_OAUTH_TOKEN (`claude setup-token`)."""
import glob
import json
import re
import os
import subprocess
import threading
import time

from . import agents, config, jobs

STEP_PT = {'prepare': 'prepare (extraction, title update, DLC, codegen, layer, build)',
           'build': 'build (rexnative project --build)',
           'boot': 'boot test on the PC (scripts/live.ps1)',
           'test': 'test'}

RULES = """Hard rules (never break them):
- The ReXNative repository is PUBLIC. Never commit anything that comes from a game: images,
  captures, XEX or archive files, extracted game files, game logs, or lists of a game's function
  addresses. Game-specific data and settings stay in the game's work folder.
- Commits use the identity {identity_name} <{identity_email}>
  (git -c user.name={identity_name} -c user.email={identity_email} commit ...) and the message ends
  with the trailer line "{trailer}". Never write anyone's private email.
- Never answer, close or kill Windows Firewall dialogs. Never kill broad sets of processes (no
  `taskkill /IM python.exe`); stop only processes you started yourself.
- Do not use the Steam Deck. Do not download games. Do not delete games, saves or downloads.
- Do not switch branches, stash or reset in shared checkouts. Work only in the ReXNative worktree
  given below and in the game's work folder.
- ReXNative is a universal renderer used by many games: a change must not break the others. That is
  a reason to GATE the change, never a reason to leave this game broken: make it apply only where it
  is needed (the game's D3D/XDK version, its title, a per-game setting or layer file, a format or
  path only it uses) so the other games keep their path, and prefer a game setting in the game's
  files when the problem is that game's alone.
- No single command longer than ~30 minutes.{extra_rules}
"""


def rules_text(cfg=None):
    """As regras com a identidade de quem usa a app (o GitHub), o trailer do assistente e as regras
    a mais desta máquina (agent_rules nas Definições)."""
    from . import github
    cfg = cfg or config.load()
    name, email = github.identity()
    extra = ''.join('\n- %s' % r for r in cfg.get('agent_rules') or [])
    return RULES.format(identity_name=name or 'rexnative-manager-user',
                        identity_email=email or 'noreply@users.noreply.github.com',
                        trailer=agents.trailer(cfg),
                        extra_rules=extra)


def push_text(cfg=None):
    """Publicar no main (quem pode) ou só fazer commit (a app abre um pull request com os commits)."""
    from . import github
    cfg = cfg or config.load()
    if not cfg.get('claude_push', True):
        return NO_PUSH
    return PUSH if github.status().get('can_push') else SHARE


def work_roots_text(cfg=None):
    cfg = cfg or config.load()
    return ' and '.join(cfg.get('work_roots') or []) or 'the work folders'

PROMPT = """You are fixing a failed step of the ReXNative pipeline (Xbox 360 games recompiled with
ReXGlue and drawn by ReXNative's native D3D12 renderer). The ReXNative Manager app ran the step
below and it failed. When you finish, the app runs the same step again (this is attempt {attempt}
of {max_attempts}).

Game: {title} (folder name {slug})
Game work folder: {work}
ReXNative worktree (your working directory; detached HEAD of github.com/{rexnative_repo}; this app's own copy, no other session works in it): {rexnative_dir}
Failed step: {step} - {step_pt}
Command: {command}
Ran in: {cwd}
Exit code: {rc}
Full log of the step: {log_path}
{details}
Last lines of the log:
```
{tail}
```
{history}
What to do:
1. Find the cause: read the full log, the game's work folder (prepare.json, codegen.log,
   run/logs/, layer/report.md) and ReXNative's code and notes in the worktree (rexnative/,
   renderer/, docs/NOTES.md, docs/GAMES.md, docs/ARCHITECTURE.md).
2. Fix it where it belongs: the game's own files in its work folder (run/<name>.toml, deck.toml,
   hints.txt, dlc-archives.txt, src/game_*.cpp) or a general fix in ReXNative.
3. Try a fix: the user wants an attempt, not "it cannot be done". When the cause is known but a
   general change looks risky for the other games, gate it (see the rules) and do it. Check that
   the game builds: `python -m rexnative project "{work}" --build` from the worktree (the
   environment already has the REXNATIVE_* variables), then check it running when you can:
   `powershell -ExecutionPolicy Bypass -File scripts\\live.ps1 start -Dir "{work}\\run" -Exe <name>.exe`,
   `live.ps1 frame <tag>` (look at the PNG), `live.ps1 log <pattern>`, and `live.ps1 stop` when
   done. Your live game has a state folder of its own (REXNATIVE_LIVE_STATE is set): no other
   session's game is in your way. Starting the game costs minutes: keep one running for the
   experiments, and for a fault at a place, `live.ps1 record 3` there and `live.ps1 play <trace>`
   after each rebuild (docs/DEBUGGING.md). The app runs the boot test again after you.
4. Commit ReXNative changes in the worktree (identity and trailer in the rules below).{push}
5. End with a SHORT summary in English for the user: the cause, what you
   changed (files, commits) and whether the retry should pass. Start it with "NO FIX:" only
   when no attempt can work now (an XNA/.NET game, hardware or an SDK feature that does not exist,
   or attempts you made and checked that failed), and then say what you tried and what is missing;
   never only because a change might affect other games (gate it instead).
   Finish the summary with these two lines, exactly in this form:
   REXNATIVE: <one short sentence: what this changed in ReXNative for every game, or "nothing">
   COMMITS: <the short hashes of the ReXNative commits YOU made (after the push), space-separated, or "none">
   SUSPECTS: <only if you committed ReXNative changes: up to 6 folder names of OTHER prepared games
   (in {work_roots}) that go through the code you changed,
   judged from their logs (run\\logs\\*.log, run\\logs\\live\\*.log) and layers, space-separated; or "none">

{rules}"""

PUSH = """ Then publish them: `git fetch origin`, `git rebase origin/main`
   and `git push origin HEAD:main`. If the rebase conflicts, `git rebase --abort` and leave the
   commit unpushed (say so in the summary)."""
NO_PUSH = ' Do not push (the user publishes them).'
SHARE = """ Do not push: you cannot publish to ReXNative directly. The app sends your commits to a
   pull request to ReXNative after the tests pass (keep the commits clean and self-explanatory)."""


def live_state_dir():
    """A pasta de estado do live.ps1 das sessões do assistente desta app: o jogo ao vivo delas é só
    delas (outras sessões no PC usam a de origem, %LOCALAPPDATA%\\rexnative-live) e nenhuma pára o
    da outra."""
    # The report lane keeps its own (config.override in pipeline.report_job): a report's live game
    # and the one of a fix in the build lane run side by side.
    return os.path.join(os.environ.get('LOCALAPPDATA', ''),
                        config.get('claude_live_state') or 'rexnative-live-manager')


def _env():
    env = config.tool_env()
    env['REXNATIVE_LIVE_STATE'] = live_state_dir()
    # Variáveis de uma sessão da app Claude que lançou esta app (não são uma sessão iniciada e
    # confundem o claude.exe filho); a ficha de setup-token e a chave da API ficam.
    for k in list(env):
        if (k.startswith('CLAUDE') and k not in ('CLAUDE_CODE_OAUTH_TOKEN',)) or \
                k in ('CLAUDECODE', 'ANTHROPIC_BASE_URL', 'USE_LOCAL_OAUTH', 'USE_STAGING_OAUTH'):
            env.pop(k, None)
    return env


def _git(args, cwd):
    r = subprocess.run(['git', '-C', cwd] + args, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', creationflags=jobs.CREATE_NO_WINDOW)
    return r.stdout.strip() if r.returncode == 0 else ''


def _describe_tool(name, inp):
    inp = inp or {}
    if name in ('Bash', 'PowerShell'):
        return '%s: %s' % (name, (inp.get('command') or '')[:300])
    if name in ('Edit', 'Write', 'Read', 'MultiEdit', 'NotebookEdit'):
        return '%s %s' % (name, inp.get('file_path') or inp.get('notebook_path') or '')
    if name in ('Grep', 'Glob'):
        return '%s %s %s' % (name, inp.get('pattern', ''), inp.get('path', '') or '')
    return '%s %s' % (name, json.dumps(inp, ensure_ascii=False)[:200])


def check():
    """Se o assistente escolhido existe e tem sessão iniciada: {'exe', 'ok', 'message'} (uma pergunta
    mínima ao modelo mais barato)."""
    if agents.name() != 'claude':
        return agents.check()
    exe = config.claude_exe()
    if not exe:
        return {'exe': None, 'ok': False, 'message': 'Claude Code not found (claude on the PATH '
                'or the Claude app for Windows); set its path in Settings.'}
    try:
        r = subprocess.run([exe, '-p', 'Answer only: ok', '--output-format', 'json',
                            '--model', 'haiku', '--no-session-persistence',
                            '--permission-mode', 'plan'], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', env=_env(), timeout=120,
                           cwd=config.data_dir(), creationflags=jobs.CREATE_NO_WINDOW)
        out = json.loads(r.stdout or '{}')
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return {'exe': exe, 'ok': False, 'message': str(e)}
    if out.get('is_error'):
        msg = out.get('result') or 'error'
        if 'login' in msg.lower():
            msg += (' — in PowerShell, run once:  & "%s" auth login  (the browser opens; '
                    'authorize it and, if asked, paste the code into PowerShell)' % exe)
        return {'exe': exe, 'ok': False, 'message': msg}
    return {'exe': exe, 'ok': True, 'message': 'signed in (%s)' % (out.get('result') or '').strip()}


SELFTEST_PROMPT = """This is a self-test of the ReXNative Manager app's automatic fix loop. A
step failed on purpose: {tail}
Fix it by editing that file only (it is in your working directory), then end with one short
sentence in English saying what you changed. Do not touch anything else."""


def ask(prompt, schema, cwd, model=None, timeout=300):
    """Uma pergunta com resposta em JSON (--json-schema) ao modelo barato, que só pode ler
    ficheiros (imagens incluídas). Devolve (resposta, custo estimado)."""
    if agents.name() != 'claude':
        return agents.ask(prompt, schema, cwd, cheap_model=model, timeout=timeout)
    exe = config.claude_exe()
    if not exe:
        raise RuntimeError('Claude Code not found')
    cfg = config.load()
    cmd = [exe, '-p', '--output-format', 'json', '--json-schema', json.dumps(schema),
           '--model', model or cfg.get('claude_cheap_model') or 'haiku',
           '--allowedTools', 'Read', '--permission-mode', 'dontAsk', '--permission-prompts', 'none',
           '--no-session-persistence']
    r = subprocess.run(cmd, input=prompt.encode('utf-8'), capture_output=True, cwd=cwd, env=_env(),
                       timeout=timeout, creationflags=jobs.CREATE_NO_WINDOW)
    try:
        out = json.loads(r.stdout.decode('utf-8', 'replace') or '{}')
    except ValueError:
        raise RuntimeError('unreadable answer from Claude: %s' % r.stdout[-300:])
    if out.get('is_error'):
        raise RuntimeError('Claude: %s' % (out.get('result') or out.get('subtype')))
    answer = out.get('structured_output')
    if answer is None:
        text = (out.get('result') or '').strip().strip('`')
        text = text[text.find('{'):text.rfind('}') + 1] if '{' in text else text
        answer = json.loads(text)
    return answer, out.get('total_cost_usd')


def fix(job, failure, attempt, history=''):
    """Corre o Claude sobre uma falha. failure: {step, title, slug, work, command, cwd, rc,
    log_path, tail, details}. Devolve {summary, commits, pushed, edited, cost, ok}."""
    cfg = config.load()
    rex = cfg['rexnative_dir']
    selftest = bool(failure.get('selftest'))
    if selftest:
        prompt = SELFTEST_PROMPT.format(tail=failure.get('tail', ''))
        rex = failure['work']
    else:
        prompt = PROMPT.format(
            attempt=attempt, max_attempts=cfg['claude_max_attempts'], rexnative_dir=rex,
            step_pt=STEP_PT.get(failure['step'], failure['step']), rules=rules_text(cfg),
            push=push_text(cfg), work_roots=work_roots_text(cfg), rexnative_repo=cfg.get('rexnative_repo'),
            history=('\nEarlier attempts in this run (what was tried):\n%s\n' % history) if history else '',
            **{k: failure.get(k, '') for k in ('title', 'slug', 'work', 'step', 'command', 'cwd',
                                                'rc', 'log_path', 'tail', 'details')})
    return run(job, prompt, cwd=rex, work=failure['work'], cheap=selftest,
               tag='%d' % attempt, intro='Claude analysing the "%s" failure (attempt %d)' % (
                   failure['step'], attempt), git=not selftest)


REPORT_PROMPT = """The user reports a problem with an Xbox 360 game recompiled with ReXGlue and drawn by
ReXNative's native D3D12 renderer. Investigate it, fix it if you can, and say what you did.

Game: {title} (folder name {slug})
Game work folder: {work}
Built game: {run}\\{name}.exe; its settings on the PC: {run}\\{name}.toml; the Deck's overrides:
{work}\\deck.toml (merged over the kit's Deck settings by `python -m rexnative deck`)
ReXNative worktree (your working directory; detached HEAD of github.com/{rexnative_repo}; this app's own copy, no other session works in it): {rexnative_dir}

The user's report:
- Kind: {kind}
- Where: {where}
- What they see: {text}
{snapshot}{captures}{boot}
Work fast. The time goes into starting the game (logos, intros, loading the save: minutes) and
into rebuilds (minutes each); an experiment on a running game or on a recorded trace takes
seconds. Aim for a fix checked on the PC within about {aim} minutes (the app stops you after
{limit}). Below, `live.ps1` is `powershell -ExecutionPolicy Bypass -File scripts\\live.ps1`. Your live
game has a state folder of its own (REXNATIVE_LIVE_STATE is set for you): no other session's game
is in your way, and you never stop someone else's.

{first_steps}3. Sort the fault before reading code (seconds each, on the live game; docs/DEBUGGING.md has the
   whole table). A trace played without the loop and dump flags keeps drawing, and `frame`,
   `capture`, `debug`, `snap`, `drawlog` and `control "set ..."` work on it as on the game:
   - Is it ReXNative's renderer? `live.ps1 control "renderer stock"`, `frame`, then
     `control "renderer native"`: ReXGlue's Xenos renderer at the same spot. Wrong there too: not
     ReXNative's renderer (the game's settings or layer, the SDK, the game itself). Right there:
     a ReXNative renderer fault.
   - Which pass goes wrong first: start with `-Oracle`, then `live.ps1 oracle` prints the first
     resolve that differs from the Xenos plugin's, in the same frame.
   - Only now and then, or only in motion: `play` the trace. Wrong in the replay: the data or the
     way it is drawn. Right in the replay: timing, or state kept from earlier frames: `record 1`
     at the fault, `play`, then `compare` names the first resolve apart; `audit` lists textures
     whose guest memory changed unseen; `idle` drops stale resolved images (a fault that goes
     with them was one).
   - Which draw, or what made a pixel: `debug "<mask> 0 <from> <to>"` skips a range of draws,
     `snap`, `drawlog`; RenderDoc: start with `-RenderDoc`, `live.ps1 capture`, then
     `scripts\\rdoc.ps1 summary <capture>`, `history -X -Y`, `inputs -Event` (delete the .rdc
     files when done: gigabytes each).
   - Not a picture (sound, controls, a crash, a freeze, slowness): the log first,
     `live.ps1 log "<pattern>"`: `ReXNative audio:` lines (underruns, channels), `the fault was
     caught` (address and code offset), the frame statistics, the SDK's crash report.
4. Search where it is small: renderer/, rexnative/ and docs/ (docs/GAMES.md: similar problems
   already fixed in other games; docs/NOTES.md is long: list its headings first,
   `Select-String '^#' docs\\NOTES.md`). Do not grep the recompiled game (generated\\, hundreds of
   MB) to find what writes some memory: `live.ps1 control "watch <address> any"` logs the
   recompiled functions that write that guest dword (`watch off` after), and `peek` / `poke`
   read and write guest memory live.
5. Fix it where it belongs: a renderer fault gets a general fix in ReXNative (renderer/,
   rexnative/), gated to where it is needed when it could change other games; a problem of this
   game alone gets the game's own settings or layer files. Make all the edits of one idea, then
   ONE rebuild: `live.ps1 stop` (the executable is locked while it runs),
   `python -m rexnative project "{work}" --build`, `play` your trace to see the result, and a last
   look in the live game at the place. Commit ReXNative changes (identity and trailer in the
   rules).{push}
6. Try a fix: the user wants an attempt, not "it cannot be done". Start the summary with
   "NO FIX:" only when no attempt can work now (or the attempts you made and checked failed),
   saying what you tried. If you could not reach the place and the player left no snapshot of it,
   say so and ask for one (in the game, at the place: View + Menu on the Deck, Back + Start or F1 on
   the PC, then Y; then Report a problem again). If ReXGlue's renderer draws it right and
   ReXNative's could not be fixed, also set `[rexnative]` `classic = true` in {run}\\{name}.toml and in {work}\\deck.toml as
   a workaround (the game then starts on the Classic renderer, with the settings HUD), and say so.
7. `live.ps1 stop` when you are done.

End with a SHORT summary in English for the user: the cause, what you changed
(files, commits), and where in the game to check that it is right (if it is still wrong there, a
snapshot of it, the settings menu and then Y, goes with the next report).
Finish the summary with these lines, exactly in this form:
REXNATIVE: <one short sentence: what this changed in ReXNative for every game, or "nothing">
COMMITS: <the short hashes of the ReXNative commits YOU made (after the push), space-separated, or "none">
SUSPECTS: <only if you committed ReXNative changes: up to 6 folder names of OTHER prepared games
(in {work_roots}) that go through the code you changed,
judged from their logs (run\\logs\\*.log, run\\logs\\live\\*.log) and layers, space-separated; or "none">
SCENE: <the trace of the place, the player's snapshot trace or one you recorded, one line each, at most 2;
leave the line out if none>

{rules}"""


CRASH_PROMPT = """An Xbox 360 game recompiled with ReXGlue and drawn by ReXNative crashed for the user, who
asks for a fix from the crash log ALONE. Do not start the game: no live.ps1, no traces, no
RenderDoc, no runs of your own (the user does not want the game opened for this; the app builds
it after you and checks once that it still starts). Read the log, find the cause in the code, fix
it, and say what you did.

Game: {title} (folder name {slug})
Game work folder: {work} (hints.txt, not-starts.txt, the manifest {name}_manifest.toml with each
module's [modules.functions], layer/, src/; generated\\ = ReXGlue's code, hundreds of MB)
Built game: {run}\\{name}.exe; its settings on the PC: {run}\\{name}.toml; the Deck's overrides:
{work}\\deck.toml
ReXNative worktree (your working directory; detached HEAD of github.com/{rexnative_repo}; this app's own copy, no other session works in it): {rexnative_dir}

The user's report:
- Where: {where}
- What they say: {text}
{logs}
1. Read the crash report: the lines from `==== <name> crash report` to `==== end of crash
   report ====`, and the `C` (critical) lines just before it: what stopped the game (a call to an
   unregistered guest function, a caught fault with its address and code offset, a failed
   assertion), the guest thread, the backtrace (module + offset). The lines before those say what
   the game was doing (loading, a menu, a race, a cutscene).
2. Sort it:
   - "Call to invalid or unregistered function at guest address 0x...", "No function registered
     at ...": a function start codegen did not discover (reached through a pointer: a callback,
     a table, a thread entry). Which module holds the address (the game's .xex or one of its
     DLLs: the log lists each module as it registers its functions). rexnative/functions.py and
     rexnative/project.py say how a work folder gets a function start (hints.txt for the .xex,
     `0xADDRESS 0xSIZE`, 0 = codegen finds the end; a DLL module through its own entry in the
     manifest), so that codegen keeps it; then codegen and the build run again
     (`python -m rexnative project "{work}" --build`). Not --discover or --find-functions: they
     start the game.
   - A fault in ReXNative's or the SDK's code (rexgpu, rexnative, a backtrace through them): the
     code at that offset; docs/DEBUGGING.md, docs/GAMES.md (similar crashes already fixed).
   - Anything else: reason from the log and the code; docs/NOTES.md is long (list its headings
     first, `Select-String '^#' docs\\NOTES.md`). Search generated\\ only for one function or
     address, never blindly.
3. Fix it where it belongs: a general fix in ReXNative when other games can hit it (gated when it
   could change them), this game's own files otherwise. Then ONE build:
   `python -m rexnative project "{work}" --build` must succeed. Commit ReXNative changes
   (identity and trailer in the rules).{push}
4. Start the summary with "NO FIX:" only when the log does not hold enough to fix it, saying what
   is missing (then a normal report, which may start the game, or a snapshot at the place).

End with a SHORT summary in English for the user: the cause, what you changed (files, commits),
and where in the game to check it.
Finish the summary with these lines, exactly in this form:
REXNATIVE: <one short sentence: what this changed in ReXNative for every game, or "nothing">
COMMITS: <the short hashes of the ReXNative commits YOU made (after the push), space-separated, or "none">
SUSPECTS: <only if you committed ReXNative changes: up to 6 folder names of OTHER prepared games
(in {work_roots}) that go through the code you changed,
judged from their logs (run\\logs\\*.log, run\\logs\\live\\*.log) and layers, space-separated; or "none">

{rules}"""


def _ends_in_crash(path):
    try:
        with open(path, 'rb') as f:
            f.seek(max(0, os.path.getsize(path) - 131072))
            return b'==== end of crash report' in f.read()
    except OSError:
        return False


def crash_logs(work, report):
    """The logs a crash-only report reads: the Deck's (deck-*.log, fetched with the report), and
    this PC's newest log of the game that ends in a crash report only when none of the Deck's does
    (an older crash on the PC, from another build, would mislead)."""
    out = [f for f in report.get('deck_files') or [] if f.lower().endswith('.log')]
    if any(_ends_in_crash(f) for f in out):
        return out
    pc = sorted(glob.glob(os.path.join(work, 'run', 'logs', '*.log')), key=os.path.getmtime, reverse=True)
    return out + next(([p] for p in pc[:10] if _ends_in_crash(p)), [])


FIRST_SNAPSHOT = """1. Start from the player's snapshot (above): no game to reach. Look at its picture, then
   `live.ps1 play "<its trace>" -Dir "{run}" -Exe {name}.exe -Extra "--rexnative_trace_play_loops=2 --rexnative_trace_play_dump=true --rexnative_trace_play_fps=0"`
   draws its frames with the PC's build and exits in about 20 s (the images:
   {run}\\live\\cap\\f<i>-native.png, from the second time through). Set them beside the picture:
   - Wrong the same way: the fault is in the game's data or in how ReXNative draws it, and this
     trace is your fast loop: after each rebuild, play it again. It is the place's test scene too.
   - Right on the PC but wrong in the picture: the difference is the machine's. Play it again with
     that machine's settings (for the Deck: copy the Deck's settings file over {run}\\{name}.toml,
     play, then put the PC's file back). Wrong now: a setting's path (the upscaler, its mode...).
     Still right: the Deck's GPU and driver under Proton; reason from the picture, the Deck's log
     and the code (you cannot use the Deck).
   - `play` says the trace does not fit this build (the PC build changed since it was taken):
     reach the place live instead (2.).
2. Reach the place live only when you need the running game (a fault the trace does not hold:
   timing, or state from earlier frames, see 3.; or the last check after the fix):
   `live.ps1 start -Dir "{run}" -Exe {name}.exe -Route "<s>:pad:A:200,..."` (`pad:` presses the
   game's own pad, no window focus needed), with the player's save (Continue or Load, never a new
   game); wait in short steps (`Start-Sleep 20`, then `live.ps1 frame <tag>`), never minutes blind.
"""

FIRST_PLACE = """1. Reach the place ONCE: `live.ps1 start -Dir "{run}" -Exe {name}.exe -Route "<s>:pad:A:200,..."`
   (`pad:` presses the game's own pad, no window focus needed; `<s>:hold:ENTER:150` sends keys).
   With the player's save, Continue or Load, never a new game. Wait in short steps
   (`Start-Sleep 20`, then `live.ps1 frame <tag>` and look at the PNG), never minutes blind.
   A problem seen on the Deck: start it with the Deck's settings (copy the Deck's settings file
   over {run}\\{name}.toml first, and put the PC's back when you are done).
2. Record it at once, before changing anything: `live.ps1 record 3` prints a frame trace (a .rxt
   in {run}\\live\\trace). It is your fast loop: after a rebuild,
   `live.ps1 play "<trace>" -Extra "--rexnative_trace_play_loops=2 --rexnative_trace_play_dump=true --rexnative_trace_play_fps=0"`
   draws those frames with the new build and exits in about 20 s (the images:
   {run}\\live\\cap\\f<i>-native.png, from the second time through), with no game to reach again.
   It is also this game's test scene: add a line `SCENE: <trace path>` after SUSPECTS (at most 2);
   the app then checks that place after every later ReXNative change. If `play` says the trace no
   longer fits the build ("record it again"), reach the place live once more and record again.
   Skip the trace only when the place cannot be reached (and see 6.).
"""


GAMEPLAY_PROMPT = """Find real gameplay in an Xbox 360 game recompiled with ReXGlue and drawn by ReXNative's
native D3D12 renderer, record a frame trace there, and look at that place on both renderers. You only
start the game, press its buttons and look: change no file, commit nothing.

Game: {title} (folder name {slug}); the built game: {run}\\{name}.exe. Below, `live.ps1` is
`powershell -ExecutionPolicy Bypass -File scripts\\live.ps1` (in your working directory); your live game
has a state folder of its own.{route_hint}

1. `live.ps1 start -Dir "{run}" -Exe {name}.exe`, then drive it with the game's own pad through the
   control file (no window focus needed): `live.ps1 control "pad A 200"`, `"pad START 400"`,
   `"pad DOWN 150"`, `"pad A+B 200"`, a stick held: `"pad none lx=32767 800"` (lx ly rx ry from
   -32768 to 32767). Look every step or two with `live.ps1 frame <tag>` and read the PNG. Wait in
   short steps (`Start-Sleep 5` to 15), never minutes blind. A lone START or BACK needs about 400 ms.
2. Real gameplay is the player controlling the game: a level, a race, a board, a fight, a puzzle in
   play. Not the title screen, menus, logos, videos, loading screens or a cutscene. Start a new game
   (or a quick match, arcade or practice mode), skip what can be skipped (A, START or B on videos and
   dialogs), accept defaults. If the game asks to overwrite a save, pick another slot or go back;
   never delete saves. A tutorial is fine once the player is playing. Give it at most {limit} minutes.
3. At gameplay, play a few seconds so things move on the screen, then `live.ps1 record 3` (it prints
   the trace's path). Then the same spot on both renderers: `live.ps1 frame native`,
   `live.ps1 control "renderer stock"`, `Start-Sleep 5`, `live.ps1 shot classic` (a window capture:
   the renderer's own `frame` works only on the native one), `live.ps1 control "renderer native"`.
   The classic one (ReXGlue's Xenos renderer) is the reference.
   Compare the two pictures: motion between them is not a fault; black or white areas, missing
   geometry or effects, wrong colours, see-through walls or garbage on the native one are.
4. `live.ps1 stop`. Stop only the game you started; do not use the Steam Deck; do not kill other
   processes.

End with these lines, exactly in this form:
SCENE: <the trace path that record printed, or "none" if gameplay was not reached>
LABEL: <a few words on where in the game it is, e.g. "first race, city circuit">
ROUTE: <the steps from the start that reached it, as <seconds waited before it>:pad:<BUTTONS>:<ms>, comma-separated, or "none">
NATIVE: <"ok", or "wrong: <what the native renderer draws wrong there, compared with the classic>">
PICTURES: <the native PNG path> <the classic PNG path>
"""

_LINE = lambda tag: re.compile(r'^\s*%s:\s*(.+?)\s*$' % tag, re.M)  # noqa: E731


def gameplay(job, work, route=None):
    """A sessão curta que leva o jogo até se estar a jogar e grava lá um trace. Devolve {summary,
    scene, label, route, native, pictures, cost, ok}; scene None se não chegou ao jogo."""
    from . import games
    cfg = config.load()
    g = games.info(work)
    name = g.get('exe') or '?'
    hint = ('\nA route that reached gameplay before (try it first, it may be out of date): %s' % route) if route else ''
    limit = int(cfg.get('gameplay_minutes') or 12)
    prompt = GAMEPLAY_PROMPT.format(title=g['title'], slug=g['slug'], run=os.path.join(work, 'run'), name=name,
                                    route_hint=hint, limit=limit)
    res = run(job, prompt, cwd=cfg['rexnative_dir'], work=work, tag='gameplay', git=False,
              intro='Claude looks for gameplay in the game, to record a scene there',
              model=cfg.get('gameplay_model') or None, effort='medium')
    text = res.get('summary') or ''
    pick = lambda tag: (_LINE(tag).search(text).group(1) if _LINE(tag).search(text) else '')  # noqa: E731
    scene = (parse_scenes(text) or [''])[0].strip().strip('`"')
    pictures = [p.strip('`"') for p in pick('PICTURES').split() if p.lower().endswith('.png')]
    return dict(res, scene=scene if scene and scene.lower() != 'none' else None, label=pick('LABEL')[:120],
                route=pick('ROUTE') if pick('ROUTE').lower() != 'none' else '', native=pick('NATIVE') or '',
                pictures=pictures)


SCENE_LINE = re.compile(r'^\s*SCENE:\s*(.+?)\s*$', re.M)


def parse_scenes(summary):
    """Os traces que o Claude gravou como cenas de teste ("SCENE: <caminho do .rxt>")."""
    return [m.group(1) for m in SCENE_LINE.finditer(summary or '')]


def pc_snapshots(run, hours=24, limit=2):
    """Os snapshots tirados neste PC (run/snapshots/<data-hora>/) nas últimas `hours` horas, os
    `limit` mais recentes: os que um relatório leva. O diálogo do relatório mostra-os."""
    import time
    pc = []
    root = os.path.join(run, 'snapshots')
    if os.path.isdir(root):
        for n in sorted(os.listdir(root))[-limit:]:
            d = os.path.join(root, n)
            if os.path.isdir(d) and time.time() - os.path.getmtime(d) < hours * 3600:
                fs = sorted(os.listdir(d))
                info = ''
                if 'snapshot.txt' in fs:
                    with open(os.path.join(d, 'snapshot.txt'), encoding='utf-8', errors='replace') as f:
                        info = ' '.join(f.read().split())[:200]
                pc.append({'name': n, 'info': info, 'where': 'this PC', 'at': os.path.getmtime(d),
                           'png': [os.path.join(d, f) for f in fs if f.endswith('.png')],
                           'trace': [os.path.join(d, f) for f in fs if f.endswith('.rxt')]})
    return pc


def _snapshots(deck_snaps, run, hours=24, only=None):
    """Os snapshots de depuração do jogador (o Y no menu de definições do ReXNative): os que vieram do
    Deck com o relatório e os tirados neste PC nas últimas `hours` horas (run/snapshots). `only`: os
    nomes dos do PC que o jogador deixou marcados no diálogo (None = todos, os relatórios de antes)."""
    pc = [s for s in pc_snapshots(run, hours) if only is None or s['name'] in only]
    return [dict(s, where='the Steam Deck') for s in deck_snaps] + pc


def _snapshots_text(snaps):
    if not snaps:
        return ''
    when = lambda n: '%s-%s-%s %s:%s' % (n[0:4], n[4:6], n[6:8], n[9:11], n[11:13]) if len(n) >= 13 else n
    lines = ''.join('  %s, on %s%s:\n    picture %s\n    trace %s\n' % (
        when(s['name']), s['where'], (' (%s)' % s['info']) if s.get('info') else '',
        ', '.join(s['png']) or 'none', ', '.join(s['trace']) or 'none (taken on the classic renderer)')
        for s in snaps)
    return ('- A snapshot the player took in the game AT THE PLACE (the settings menu, then Y). The picture is '
            'the frame as it was shown: what the player saw, look at it first. The trace holds the next frames as '
            'the game handed them to the renderer, recorded by that machine\'s build of this same executable:\n%s'
            % lines)


def _scenes_text(slug, run, name):
    """As cenas de teste do jogo (traces gravados em sítios dele): tocam-se já, sem chegar lá."""
    from . import scenes
    out = []
    for m in scenes.scenes(slug)[-6:]:
        trace = os.path.join(scenes.scene_dir(slug, m['id']), 'scene.rxt')
        if os.path.exists(trace):
            out.append('  %s (%s)%s: %s\n' % (m.get('label') or m['id'], m.get('source') or '?',
                                               ', recorded by an older build: may need recording again'
                                               if m.get('stale') else '', trace))
    if not out:
        return ''
    return ('Test scenes of this game, frame traces recorded at places in it (no need to reach them: '
            '`live.ps1 play "<trace>" -Dir "%s" -Exe %s.exe` draws them with the current build):'
            '\n%s' % (run, name, ''.join(out)))


def investigate(job, work, report):
    """O Claude (modelo forte) investiga um relatório do utilizador e corrige o que puder."""
    from . import games
    cfg = config.load()
    rex = cfg['rexnative_dir']
    g = games.info(work)
    name = g.get('exe') or '?'
    caps = report.get('captures') or []
    snaps = _snapshots(report.get('snapshots') or [], os.path.join(work, 'run'),
                       only=report.get('pc_snapshots'))
    snap_pngs = {os.path.normcase(p) for sn in snaps for p in sn['png']}
    shown = [c for c in caps if os.path.normcase(c) not in snap_pngs]
    captures = ('Captures the user attached (look at them):\n' + ''.join('  %s\n' % c for c in shown)) if shown else ''
    boot = g.get('boot') or {}
    boot_txt = ''
    if boot:
        boot_txt = ('Last boot test on the PC (%s): running=%s, %d frames, %.1f draws/frame, %.1f ms/frame, '
                    'log %s%s\n' % (boot.get('at'), boot.get('running'), boot.get('frames') or 0,
                                    boot.get('draws') or 0, boot.get('frame_ms') or 0, boot.get('log'),
                                    (', its capture %s' % boot['shot']) if boot.get('shot') else ''))
    boot_txt += _scenes_text(g['slug'], os.path.join(work, 'run'), name)
    deck_files = report.get('deck_files') or []
    if deck_files or report.get('where') == 'Steam Deck':
        boot_txt += ('Seen on the STEAM DECK (AMD GPU, Proton, its own settings: 1280x800 and the upscaler '
                     'on by default), not necessarily on the PC. Reproduce it on the PC with the Deck\'s '
                     'settings before concluding the PC is fine: the Deck\'s settings file is below '
                     '(deck-{name}.toml; deck/{name}-deck.toml in the work folder is what the kit installs).\n'
                     .replace('{name}', name))
        if deck_files:
            boot_txt += 'Files from the Deck (its game log, its settings, captures):\n' + ''.join(
                '  %s\n' % f for f in deck_files)
    sv = report.get('saves') or {}
    if sv.get('files'):
        boot_txt += ("The player's saves from the Deck are in the PC copy now (%s, %d files; %s): the game "
                     "starts with the player's progress. Load it (continue or load, not a new game) to reach "
                     "the place in the report, which may only open with that progress. Do not delete them.\n"
                     % (sv.get('run'), sv['files'],
                        "the PC's own saves from before are in %s" % sv['backup'] if sv.get('backup')
                        else 'the PC had no saves of its own'))
    deck_log = os.path.join(work, 'deck', 'try.log')
    if os.path.exists(deck_log):
        boot_txt += 'Last try on the Steam Deck: log %s (captures in %s)\n' % (
            deck_log, os.path.join(work, 'deck'))
    limit = int(float(cfg.get('claude_timeout_min') or 120))
    if report.get('crash_only'):
        logs = crash_logs(work, report)
        logs_txt = ("The logs (the Deck's are deck-*.log; the crash report is at the end of the one "
                    'that crashed):\n' + ''.join('  %s\n' % f for f in logs)) if logs else (
                    'No log with a crash report was found (on the Deck or on this PC): say so with NO FIX.\n')
        prompt = CRASH_PROMPT.format(
            title=g['title'], slug=g['slug'], work=work, run=os.path.join(work, 'run'), name=name,
            rexnative_dir=rex, rexnative_repo=cfg.get('rexnative_repo'), where=report.get('where', '-'),
            text=report.get('text', '').strip() or '-', logs=logs_txt, push=push_text(cfg),
            rules=rules_text(cfg), work_roots=work_roots_text(cfg))
        return run(job, prompt, cwd=rex, work=work, tag='report',
                   intro='Claude reads the crash log (%s): the game does not open' % report.get('where'),
                   extra_dirs=sorted({os.path.dirname(f) for f in logs}))
    run_dir = os.path.join(work, 'run')
    with_trace = any(sn['trace'] for sn in snaps)
    prompt = REPORT_PROMPT.format(
        snapshot=_snapshots_text(snaps),
        first_steps=(FIRST_SNAPSHOT if with_trace else FIRST_PLACE).format(run=run_dir, name=name),
        aim=max(15, min(45, limit // 2)), limit='%d minutes' % limit,
        title=g['title'], slug=g['slug'], work=work, run=os.path.join(work, 'run'), name=name,
        rexnative_dir=rex, kind=report.get('kind', '-'), where=report.get('where', '-'),
        text=report.get('text', '').strip() or '-', captures=captures, boot=boot_txt,
        push=push_text(cfg), rules=rules_text(cfg), work_roots=work_roots_text(cfg),
        rexnative_repo=cfg.get('rexnative_repo'))
    return run(job, prompt, cwd=rex, work=work, tag='report',
               intro='Claude investigates the report (%s, %s)' % (report.get('kind'), report.get('where')),
               extra_dirs=sorted({os.path.dirname(c) for c in caps + deck_files}) + [config.data_dir('compare')])


def run(job, prompt, cwd, work, cheap=False, tag='1', intro='Claude', git=True, extra_dirs=(),
        model=None, effort=None):
    """Corre o Claude com o pedido pelo stdin e a saída em stream-json (cada texto e ferramenta
    aparece na tarefa); devolve {summary, commits, pushed, edited, cost, ok, gave_up}."""
    cfg = config.load()
    ag = agents.name(cfg)
    if ag != 'claude':
        return _run_with(job, prompt, cwd, work, cheap, tag, intro, git, ag)
    exe = config.claude_exe()
    if not exe:
        raise RuntimeError('Claude Code not found: set its path in Settings')
    # A entrada também em stream-json: o stdin fica aberto e o jogador pode escrever-lhe enquanto
    # trabalha (a mensagem entra no turno que está a correr); fecha-se no resultado.
    cmd = [exe, '-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
           '--permission-mode', cfg['claude_permission_mode'] or 'auto',
           '--permission-prompts', 'none', '--no-session-persistence',
           '--add-dir', work, '--add-dir', config.data_dir('logs')]
    for root in config.load().get('work_roots') or []:
        if os.path.isdir(root) and os.path.normcase(root) not in os.path.normcase(work):
            cmd += ['--add-dir', root]
    for d in sorted(set(extra_dirs)):
        if d and os.path.isdir(d):
            cmd += ['--add-dir', d]
    if model:
        cmd += ['--model', model]
        if effort:
            cmd += ['--effort', effort]
    elif cheap:
        cmd += ['--model', cfg.get('claude_cheap_model') or 'haiku']
    else:
        if cfg['claude_model']:
            cmd += ['--model', cfg['claude_model']]
        if cfg.get('claude_effort'):
            cmd += ['--effort', cfg['claude_effort']]
    if str(cfg.get('claude_budget_usd') or '').strip():
        cmd += ['--max-budget-usd', str(cfg['claude_budget_usd']).strip()]
    return _session(job, cmd, True, prompt, cwd, git, tag, intro, _handle, exe, 'Claude', chat=True)


def _run_with(job, prompt, cwd, work, cheap, tag, intro, git, ag):
    """Uma sessão de trabalho com outro assistente (Codex, Gemini, Antigravity): o comando e a leitura
    dos eventos são os dele (agents.py); o resto é o mesmo do Claude."""
    cfg = config.load()
    exe = agents.exe(cfg)
    if not exe:
        raise RuntimeError('%s not found: install it, or set its path in Settings' % agents.NAMES[ag])
    prompt_file = os.path.join(config.data_dir('logs'), '%s-task-%s.md' % (job.id, tag))
    cmd, via_stdin = agents.command(cfg, cwd, work, cheap, prompt_file)
    if not via_stdin:
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)

    def handle(job_, line, result, edited):
        agents.handle(ag, job_, line, result, edited, _describe_tool)
    return _session(job, cmd, via_stdin, prompt, cwd, git, tag, intro.replace('Claude', agents.NAMES[ag]),
                    handle, exe, agents.NAMES[ag])


def _user_line(text):
    return (json.dumps({'type': 'user', 'message': {'role': 'user', 'content': [
        {'type': 'text', 'text': text}]}}) + '\n').encode('utf-8')


CHAT_INTRO = ('A message from the player, written in the Manager (on the PC or the Steam Deck) while you '
              'work. Take it into account, answer it briefly in your next reply, and carry on:\n\n')


def _session(job, cmd, via_stdin, prompt, cwd, git, tag, intro, handle, exe, who, chat=False):
    """Corre a sessão (o pedido pelo stdin, ou já num ficheiro), mostra o que vai fazendo, para-a no
    tempo limite, e no fim vê os commits que fez e se os publicou. chat: o pedido vai como mensagem
    stream-json e o stdin fica aberto até ao resultado, para o jogador lhe escrever (job._say)."""
    git = git and os.path.isdir(os.path.join(cwd, '.git')) or (git and os.path.isfile(os.path.join(cwd, '.git')))
    head_before = _git(['rev-parse', 'HEAD'], cwd) if git else ''
    raw_path = os.path.join(config.data_dir('logs'), '%s-claude-%s.jsonl' % (job.id, tag))
    job.event('claude', intro, raw=raw_path)
    job.log('$ %s  (prompt on stdin; stream in %s)' % (' '.join(cmd[:3]), raw_path))
    p = subprocess.Popen(cmd, cwd=cwd if os.path.isdir(cwd) else None, env=_env(),
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         creationflags=jobs.CREATE_NO_WINDOW | jobs.CREATE_NEW_PROCESS_GROUP)
    job._proc = p
    lock = threading.Lock()
    stdin_open = [True]

    def close_stdin():
        with lock:
            job._say = None
            if stdin_open[0]:
                stdin_open[0] = False
                try:
                    p.stdin.close()
                except OSError:
                    pass

    if chat:
        p.stdin.write(_user_line(prompt))
        p.stdin.flush()

        def say(text):
            with lock:
                if not stdin_open[0]:
                    raise RuntimeError('%s has finished: write in a new report' % who)
                p.stdin.write(_user_line(CHAT_INTRO + text))
                p.stdin.flush()
            job.event('claude-user', text)

        job._say = say
    else:
        if via_stdin:
            p.stdin.write(prompt.encode('utf-8'))
        close_stdin()
    result = {}
    edited = []
    lines = []

    def reader():
        with open(raw_path, 'wb') as raw:
            for line in iter(p.stdout.readline, b''):
                raw.write(line)
                raw.flush()
                lines.append(line)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    seen = 0
    # Um limite para a sessão (a pista de compilar é uma só: uma sessão presa parava a fila toda) e,
    # se o Claude já saiu mas um processo que ele lançou ficou com a saída aberta, não se espera
    # pelo fim dela.
    limit = time.time() + 60 * float(config.load().get('claude_timeout_min') or 120)
    exited = None
    try:
        while True:
            while seen < len(lines):
                handle(job, lines[seen], result, edited)
                if chat and stdin_open[0] and b'"type":"result"' in lines[seen].replace(b' ', b''):
                    close_stdin()  # o turno acabou: sem stdin, a sessão termina
                seen += 1
            if not t.is_alive() and seen >= len(lines):
                break
            if job._cancel.is_set():
                job.kill()
                raise jobs.Cancelled()
            if time.time() > limit:
                job.event('fail', '%s took longer than %s min: stopped' % (who, config.load().get('claude_timeout_min', 120)))
                job.kill()
                break
            if p.poll() is not None:
                exited = exited or time.time()
                if time.time() - exited > 15:
                    break
            time.sleep(0.3)
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            job.kill()
        while seen < len(lines):
            handle(job, lines[seen], result, edited)
            seen += 1
    finally:
        close_stdin()
        job._proc = None
    head_after = _git(['rev-parse', 'HEAD'], cwd) if git else ''
    commits = []
    if head_before and head_after and head_before != head_after:
        commits = _git(['log', '--format=%h %s', '%s..%s' % (head_before, head_after)], cwd).splitlines()
    pushed = None
    if commits:
        pushed = subprocess.run(['git', '-C', cwd, 'merge-base', '--is-ancestor', 'HEAD',
                                 'origin/main'], capture_output=True,
                                creationflags=jobs.CREATE_NO_WINDOW).returncode == 0
    summary = (result.get('result') or '').strip()
    rex_note, claimed = parse_final(summary)
    suspects = parse_suspects(summary)
    # Só os commits do Claude: os que ele diz que fez, ou os do intervalo que mexem em ficheiros que
    # ele editou (numa pasta partilhada, outras sessões fazem commits no mesmo intervalo).
    commits = own_commits(cwd, commits, claimed, edited) if git else commits
    out = {'summary': summary, 'commits': commits, 'pushed': pushed, 'edited': sorted(set(edited)),
           'rex_note': rex_note, 'claimed': claimed, 'suspects': suspects,
           'cost': result.get('total_cost_usd'), 'turns': result.get('num_turns'),
           'ok': bool(result) and result.get('is_error') is False, 'raw': raw_path,
           'gave_up': _gave_up(summary)}
    if not result or result.get('is_error') is None:
        out['summary'] = '%s finished without a result (code %s): see %s' % (who, p.returncode, raw_path)
    elif result.get('is_error'):
        out['summary'] = '%s error: %s' % (who, result.get('result') or result.get('subtype'))
        if 'login' in out['summary'].lower() or 'auth' in out['summary'].lower():
            out['summary'] += ' — sign in: %s' % agents.LOGIN_HELP[agents.name()]
    job.event('claude', out['summary'], commits=commits, pushed=pushed, edited=out['edited'],
              cost=out['cost'], final=True)
    return out


def _gave_up(summary):
    """O resumo começa por NO FIX (também em negrito, **NO FIX:**, ou com espaços); os resumos
    antigos, SEM CORREÇÃO."""
    first = (summary or '').lstrip(' *_#>\n').upper()
    # "NO FIX:" (ou **NO FIX**: / NO FIX —), não "No fix needed".
    return bool(re.match(r'NO FIX[\s*_]*(?:[:\-—]|$)', first)) or \
        first.startswith(('SEM CORREÇÃO', 'SEM CORRECAO'))


def parse_final(summary):
    """(nota do contributo, [hashes]) das linhas REXNATIVE: e COMMITS: do fim do resumo."""
    note, hashes = None, []
    for line in (summary or '').splitlines():
        t = line.strip().strip('*').strip()
        if t.upper().startswith('REXNATIVE:'):
            note = t.split(':', 1)[1].strip().strip('*').strip() or None
        elif t.upper().startswith('COMMITS:'):
            hashes = re.findall(r'\b[0-9a-f]{7,40}\b', t.split(':', 1)[1])
    if note and note.lower().strip('."') in ('nada', 'nothing', 'none'):
        note = None
    return note, hashes


def parse_suspects(summary):
    """As pastas de jogos da linha SUSPECTS: (ou SUSPEITOS:, nos resumos antigos) do fim do resumo."""
    for line in (summary or '').splitlines():
        t = line.strip().strip('*').strip()
        if t.upper().startswith(('SUSPECTS:', 'SUSPEITOS:')):
            return [x for x in re.findall(r'[a-z0-9][a-z0-9-]{2,}', t.split(':', 1)[1].lower())
                    if x not in ('nenhum', 'none')][:6]
    return []


def own_commits(cwd, commits, claimed, edited):
    """Dos commits do intervalo ("hash assunto"), os do Claude; mais os que ele declarou fora do
    intervalo (feitos depois de um rebase)."""
    edited_rel = set()
    for f in edited or []:
        try:
            edited_rel.add(os.path.relpath(f, cwd).replace('\\', '/').lower())
        except ValueError:
            pass
    keep = []
    for c in commits:
        h = c.split(' ', 1)[0]
        if any(x.startswith(h) or h.startswith(x) for x in claimed):
            keep.append(c)
            continue
        files = {x.strip().lower() for x in _git(['show', '--name-only', '--format=', h], cwd).splitlines() if x.strip()}
        if files & edited_rel:
            keep.append(c)
    for x in claimed:
        if not any(c.split(' ', 1)[0].startswith(x[:7]) for c in keep):
            line = _git(['log', '-1', '--format=%h %s', x], cwd)
            if line:
                keep.append(line)
    return keep


def _handle(job, line, result, edited):
    try:
        m = json.loads(line.decode('utf-8', 'replace'))
    except ValueError:
        text = line.decode('utf-8', 'replace').strip()
        if text:
            job.log('claude: ' + text)
        return
    t = m.get('type')
    if t == 'assistant':
        for c in (m.get('message') or {}).get('content') or []:
            if c.get('type') == 'text' and c.get('text', '').strip():
                job.event('claude-text', c['text'].strip()[:2000])
            elif c.get('type') == 'tool_use':
                inp = c.get('input') or {}
                if c.get('name') in ('Edit', 'Write', 'MultiEdit', 'NotebookEdit'):
                    edited.append(inp.get('file_path') or inp.get('notebook_path') or '')
                job.event('claude-tool', _describe_tool(c.get('name'), inp))
    elif t == 'result':
        result.update(m)
    elif t == 'system' and m.get('subtype') == 'init':
        job.log('claude: session %s, model %s, mode %s' % (
            m.get('session_id'), m.get('model'), m.get('permissionMode')))
