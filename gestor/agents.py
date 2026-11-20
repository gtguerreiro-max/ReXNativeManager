"""Os assistentes que corrigem e investigam: Claude Code (o de origem), OpenAI Codex (entra-se com a
conta do ChatGPT), Gemini CLI e Antigravity CLI (Google). Nem toda a gente tem o Claude.

Cada um corre sem perguntas, com o pedido pelo stdin (ou num ficheiro), e escreve eventos em JSON por
linha; aqui está, para cada um: o comando, como ler os eventos (o texto, as ferramentas, os
ficheiros mudados, o fim), a pergunta curta com imagens e resposta em JSON (o modelo barato: comparar
capturas, escolher capas) e a verificação da sessão. O resto (o tempo limite, os commits feitos, o
que publicou) é o mesmo para todos (claude.run).

Modelo local: o Codex em modo OSS (`codex exec --oss --local-provider ollama|lmstudio -m <modelo>`),
com os mesmos eventos do Codex; as perguntas curtas com imagens vão direitas ao servidor local
(Ollama: /api/chat com images e format = o esquema JSON; LM Studio: /v1/chat/completions com
response_format), porque o modelo de programar (gpt-oss) não vê imagens.

Codex: `codex exec --json` (eventos thread.started, item.completed {agent_message, command_execution,
file_change}, turn.completed / turn.failed); Gemini CLI: `--output-format stream-json` (message,
tool_use, tool_result, result); Antigravity: `agy -p ... --output-format stream-json` (step_update,
result). Só o Claude Code foi experimentado nesta app; os outros seguem a documentação de cada um."""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request

from . import config, jobs

NAMES = {'claude': 'Claude Code', 'codex': 'OpenAI Codex', 'gemini': 'Gemini CLI', 'antigravity': 'Antigravity CLI',
         'local': 'Local model (Ollama or LM Studio)'}
EXE = {'claude': 'claude', 'codex': 'codex', 'gemini': 'gemini', 'antigravity': 'agy', 'local': 'codex'}
# Os modelos locais de origem: um de programar com ferramentas e um que vê imagens.
LOCAL_MODEL = 'gpt-oss:20b'
LOCAL_VISION = 'gemma3'
LOCAL_URL = {'ollama': 'http://127.0.0.1:11434', 'lmstudio': 'http://127.0.0.1:1234'}
TRAILER = {'claude': 'Co-Authored-By: Claude <noreply@anthropic.com>',
           'codex': 'Co-Authored-By: OpenAI Codex <codex@openai.com>',
           'gemini': 'Co-Authored-By: Gemini <gemini@google.com>',
           'antigravity': 'Co-Authored-By: Gemini <gemini@google.com>',
           'local': 'Co-Authored-By: Local model <noreply@localhost>'}
LOGIN_HELP = {'claude': 'run `claude` once in PowerShell and sign in (or `claude auth login`)',
              'codex': 'run `codex login` once in PowerShell (sign in with your ChatGPT account)',
              'gemini': 'run `gemini` once in PowerShell and choose Sign in with Google, or set GEMINI_API_KEY',
              'antigravity': 'run `agy` once in PowerShell and sign in with your Google account',
              'local': 'start Ollama (or LM Studio) and get the models: `ollama pull gpt-oss:20b` and '
                       '`ollama pull gemma3`; install Codex (`npm i -g @openai/codex`), which drives the local model'}


def name(cfg=None):
    a = (cfg or config.load()).get('agent') or 'claude'
    return a if a in NAMES else 'claude'


def exe(cfg=None):
    cfg = cfg or config.load()
    a = name(cfg)
    if a == 'claude':
        return config.claude_exe()
    if cfg.get('agent_exe') and os.path.exists(cfg['agent_exe']):
        return cfg['agent_exe']
    found = shutil.which(EXE[a])
    if found:
        return found
    for d in (os.path.join(os.environ.get('APPDATA', ''), 'npm'), os.path.join(os.path.expanduser('~'), '.local', 'bin')):
        for ext in ('.cmd', '.exe', ''):
            p = os.path.join(d, EXE[a] + ext)
            if os.path.exists(p):
                return p
    return None


def trailer(cfg=None):
    cfg = cfg or config.load()
    return cfg.get('agent_trailer') or TRAILER[name(cfg)]


def model(cfg, cheap):
    a = name(cfg)
    if a == 'claude':
        return cfg.get('claude_cheap_model') or 'haiku' if cheap else cfg.get('claude_model')
    if a == 'local':
        return cfg.get('agent_cheap_model' if cheap else 'agent_model') or (LOCAL_VISION if cheap else LOCAL_MODEL)
    return cfg.get('agent_cheap_model' if cheap else 'agent_model') or None


def local_provider(cfg=None):
    p = (cfg or config.load()).get('local_provider') or 'ollama'
    return p if p in LOCAL_URL else 'ollama'


def local_url(cfg=None):
    cfg = cfg or config.load()
    return (cfg.get('local_url') or LOCAL_URL[local_provider(cfg)]).rstrip('/')


# -- os comandos --------------------------------------------------------------------------------
def command(cfg, cwd, work, cheap, prompt_file):
    """O comando de uma sessão de trabalho (corrigir ou investigar) de um assistente que não é o
    Claude. Devolve (cmd, prompt_pelo_stdin)."""
    a, x, m = name(cfg), exe(cfg), model(cfg, cheap)
    if a == 'local':
        # O Codex com o modelo local (Ollama ou LM Studio): os mesmos eventos que com a OpenAI.
        # (Mesmo nas sessões "baratas" usa o modelo de programar: o que vê imagens não usa ferramentas.)
        return [x, 'exec', '--json', '--oss', '--local-provider', local_provider(cfg), '-m', model(cfg, False),
                '-C', cwd, '--skip-git-repo-check', '--sandbox', 'danger-full-access', '-'], True
    if a == 'codex':
        cmd = [x, 'exec', '--json', '-C', cwd, '--skip-git-repo-check',
               # Tem de escrever na pasta do jogo e correr compilações e o jogo: o mesmo que o modo
               # automático do Claude Code.
               '--sandbox', 'danger-full-access']
        if m:
            cmd += ['-m', m]
        return cmd + ['-'], True
    if a == 'gemini':
        cmd = [x, '--output-format', 'stream-json', '--approval-mode', 'yolo', '--skip-trust',
               '--include-directories', work]
        if m:
            cmd += ['-m', m]
        return cmd, True
    # Antigravity: o pedido num ficheiro (o -p leva só a indicação).
    cmd = [x, '-p', 'Read the task in the file %s and do it.' % prompt_file,
           '--output-format', 'stream-json', '--dangerously-skip-permissions']
    if m:
        cmd += ['-m', m]
    return cmd, False


def handle(a, job, line, result, edited, describe):
    """Uma linha de eventos de um assistente que não é o Claude: o texto e as ferramentas aparecem na
    tarefa; result fica com 'result' (o texto final), 'is_error' e o uso."""
    try:
        m = json.loads(line.decode('utf-8', 'replace'))
    except ValueError:
        t = line.decode('utf-8', 'replace').strip()
        if t:
            job.log('%s: %s' % (a, t))
        return
    if a in ('codex', 'local'):
        t = m.get('type')
        it = m.get('item') or {}
        if t == 'item.completed':
            k = it.get('type')
            if k == 'agent_message' and (it.get('text') or '').strip():
                result['result'] = it['text'].strip()
                job.event('claude-text', it['text'].strip()[:2000])
            elif k == 'command_execution':
                job.event('claude-tool', 'Shell: %s' % str(it.get('command') or '')[:200])
            elif k == 'file_change':
                for ch in it.get('changes') or []:
                    edited.append(ch.get('path') or '')
                    job.event('claude-tool', '%s %s' % ((ch.get('kind') or 'edit').capitalize(), ch.get('path')))
        elif t == 'turn.completed':
            result['is_error'] = False
            result['usage'] = m.get('usage')
        elif t in ('turn.failed', 'error'):
            result['is_error'] = True
            result.setdefault('result', str((m.get('error') or {}).get('message') or m.get('message') or 'error'))
        elif t == 'thread.started':
            job.log('codex: thread %s' % m.get('thread_id'))
        return
    if a == 'gemini':
        t = m.get('type')
        if t == 'message' and m.get('role') == 'assistant':
            result['result'] = result.get('result', '') + (m.get('content') or '') if m.get('delta') else (m.get('content') or '')
        elif t == 'tool_use':
            p = m.get('parameters') or {}
            if m.get('tool_name') in ('write_file', 'replace', 'edit'):
                edited.append(p.get('file_path') or p.get('absolute_path') or '')
            job.event('claude-tool', describe(m.get('tool_name'), p))
        elif t == 'result':
            result['is_error'] = m.get('status') != 'success'
            result['usage'] = m.get('stats')
            if m.get('error') and not result.get('result'):
                result['result'] = str(m.get('error'))
        elif t == 'error':
            job.log('gemini: %s' % m.get('message'))
        return
    # Antigravity
    t = m.get('type')
    if t == 'step_update':
        if m.get('text_delta'):
            result['result'] = result.get('result', '') + m['text_delta']
        if m.get('tool_name'):
            job.event('claude-tool', '%s %s' % (m['tool_name'], str(m.get('tool_info') or '')[:160]))
    elif t == 'result':
        result['is_error'] = str(m.get('status') or '').upper() != 'SUCCESS'
        if m.get('response'):
            result['result'] = m['response']
        result['usage'] = m.get('usage')


# -- a pergunta curta (o modelo barato) -----------------------------------------------------------
def _images(prompt, cwd):
    """As imagens que o pedido nomeia e estão na pasta (os outros assistentes recebem-nas à parte)."""
    out = []
    for tok in prompt.replace('\n', ' ').split():
        t = tok.strip('.,;:()"\'`')
        if t.lower().endswith(('.png', '.jpg', '.jpeg')) and os.path.isfile(os.path.join(cwd, t)):
            out.append(t)
    return sorted(set(out))


def _json_from(text):
    text = (text or '').strip().strip('`')
    if '{' in text:
        text = text[text.find('{'):text.rfind('}') + 1]
    return json.loads(text)


def ask(prompt, schema, cwd, cheap_model=None, timeout=300):
    """A pergunta com resposta em JSON a um assistente que não é o Claude. (resposta, custo=None)."""
    cfg = config.load()
    a, x = name(cfg), exe(cfg)
    if a == 'local':
        return _ask_local(cfg, prompt, schema, cwd, cheap_model, timeout)
    if not x:
        raise RuntimeError('%s not found: install it or set its path in Settings' % NAMES[a])
    m = cheap_model or model(cfg, True)
    imgs = _images(prompt, cwd)
    full = prompt + '\n\nAnswer with JSON only, matching this JSON schema:\n' + json.dumps(schema)
    if a == 'codex':
        d = tempfile.mkdtemp(prefix='gestor-ask-')
        sf, of = os.path.join(d, 'schema.json'), os.path.join(d, 'answer.json')
        with open(sf, 'w', encoding='utf-8') as f:
            json.dump(schema, f)
        cmd = [x, 'exec', '--json', '--ephemeral', '--skip-git-repo-check', '-C', cwd, '--sandbox', 'read-only',
               '--output-schema', sf, '-o', of]
        if m:
            cmd += ['-m', m]
        for i in imgs:
            cmd += ['-i', os.path.join(cwd, i)]
        cmd += ['--', '-']
        r = subprocess.run(cmd, input=prompt.encode('utf-8'), capture_output=True, cwd=cwd, timeout=timeout,
                           creationflags=jobs.CREATE_NO_WINDOW)
        try:
            with open(of, encoding='utf-8') as f:
                return _json_from(f.read()), None
        except (OSError, ValueError):
            raise RuntimeError('no answer from Codex: %s' % r.stdout.decode('utf-8', 'replace')[-300:])
        finally:
            shutil.rmtree(d, ignore_errors=True)
    if a == 'gemini':
        cmd = [x, '--output-format', 'json', '--approval-mode', 'yolo', '--skip-trust',
               '-p', ' '.join('@' + i for i in imgs) or 'Answer the question above.']
        if m:
            cmd += ['-m', m]
        r = subprocess.run(cmd, input=full.encode('utf-8'), capture_output=True, cwd=cwd, timeout=timeout,
                           creationflags=jobs.CREATE_NO_WINDOW)
        try:
            out = json.loads(r.stdout.decode('utf-8', 'replace') or '{}')
        except ValueError:
            raise RuntimeError('unreadable answer from Gemini: %s' % r.stdout[-300:])
        if out.get('error'):
            raise RuntimeError('Gemini: %s' % out['error'])
        return _json_from(out.get('response')), None
    # Antigravity: o pedido num ficheiro, a resposta em structured_output (--json-schema).
    pf = os.path.join(cwd, 'gestor-question.txt')
    with open(pf, 'w', encoding='utf-8') as f:
        f.write(prompt + ('\nImages: ' + ', '.join(imgs) if imgs else ''))
    try:
        cmd = [x, '-p', 'Read the question in gestor-question.txt (and the images it names) and answer it.',
               '--output-format', 'json', '--json-schema', json.dumps(schema), '--dangerously-skip-permissions']
        if m:
            cmd += ['-m', m]
        r = subprocess.run(cmd, capture_output=True, cwd=cwd, timeout=timeout, creationflags=jobs.CREATE_NO_WINDOW)
        out = json.loads(r.stdout.decode('utf-8', 'replace') or '{}')
        if str(out.get('status') or '').upper() != 'SUCCESS':
            raise RuntimeError('Antigravity: %s' % (out.get('error') or out.get('status')))
        return out.get('structured_output') or _json_from(out.get('response')), None
    except ValueError:
        raise RuntimeError('unreadable answer from Antigravity')
    finally:
        try:
            os.remove(pf)
        except OSError:
            pass


def _post(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def _ask_local(cfg, prompt, schema, cwd, cheap_model, timeout):
    """A pergunta curta ao servidor local, com as imagens que o pedido nomeia: Ollama (/api/chat,
    images e format = o esquema) ou LM Studio (/v1/chat/completions, compatível com a OpenAI)."""
    m = cheap_model or model(cfg, True)
    imgs = []
    for i in _images(prompt, cwd):
        with open(os.path.join(cwd, i), 'rb') as f:
            imgs.append((i, base64.b64encode(f.read()).decode('ascii')))
    text = prompt + '\n\nAnswer with JSON only, matching this JSON schema:\n' + json.dumps(schema)
    try:
        if local_provider(cfg) == 'ollama':
            out = _post(local_url(cfg) + '/api/chat', {
                'model': m, 'stream': False, 'format': schema, 'options': {'temperature': 0},
                'messages': [{'role': 'user', 'content': text, 'images': [b for _, b in imgs]}]}, timeout)
            return _json_from((out.get('message') or {}).get('content')), None
        content = [{'type': 'text', 'text': text}] + [
            {'type': 'image_url', 'image_url': {'url': 'data:image/%s;base64,%s' % (
                'png' if n.lower().endswith('.png') else 'jpeg', b)}} for n, b in imgs]
        out = _post(local_url(cfg) + '/v1/chat/completions', {
            'model': m, 'temperature': 0, 'messages': [{'role': 'user', 'content': content}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'answer', 'schema': schema}}}, timeout)
        return _json_from(out['choices'][0]['message']['content']), None
    except (OSError, ValueError, KeyError, IndexError) as e:
        raise RuntimeError('local model (%s at %s, model %s): %s' % (local_provider(cfg), local_url(cfg), m, e))


def _check_local(cfg, x):
    """O servidor local responde, tem os dois modelos, e o Codex (que conduz o de programar) existe."""
    base = {'agent': NAMES['local'], 'exe': x}
    url, prov = local_url(cfg), local_provider(cfg)
    try:
        with urllib.request.urlopen(url + ('/api/tags' if prov == 'ollama' else '/v1/models'), timeout=10) as r:
            d = json.loads(r.read().decode('utf-8', 'replace'))
    except (OSError, ValueError):
        return dict(base, ok=False, message='%s is not running at %s: start it (Ollama: the Ollama app or '
                                            '`ollama serve`; LM Studio: its local server)' % (prov, url))
    have = [x_.get('name') or x_.get('model') for x_ in d.get('models') or []] if prov == 'ollama' else \
        [x_.get('id') for x_ in d.get('data') or []]
    want = [model(cfg, False), model(cfg, True)]

    def present(w):
        return any(h == w or (h or '').split(':')[0] == w or (h or '').startswith(w + ':') for h in have)
    missing = [w for w in want if not present(w)]
    if missing:
        return dict(base, ok=False, message='%s answers, but these models are missing: %s (%s)' % (
            prov, ', '.join(missing), 'ollama pull ' + ' / ollama pull '.join(missing) if prov == 'ollama' else 'load them in LM Studio'))
    if not x:
        return dict(base, ok=False, message='%s and the models are ready, but Codex is missing: npm i -g @openai/codex' % prov)
    return dict(base, ok=True, message='%s at %s with %s; Codex drives the coding model' % (prov, url, ', '.join(want)))


def check():
    """Se o assistente escolhido existe e tem sessão: {'agent', 'exe', 'ok', 'message'}."""
    cfg = config.load()
    a, x = name(cfg), exe(cfg)
    if a == 'local':
        return _check_local(cfg, x)
    base = {'agent': NAMES[a], 'exe': x}
    if not x:
        return dict(base, ok=False, message='%s not found: install it, or set its path in Settings' % NAMES[a])
    try:
        if a == 'codex':
            r = subprocess.run([x, 'login', 'status'], capture_output=True, text=True, timeout=60,
                               creationflags=jobs.CREATE_NO_WINDOW)
            ok = r.returncode == 0
            return dict(base, ok=ok, message=('signed in: ' + (r.stdout or r.stderr).strip()[-120:]) if ok
                        else 'not signed in: %s' % LOGIN_HELP[a])
        answer, _ = ask('Answer with {"ok": true}.', {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                                                      'required': ['ok']}, config.data_dir(), timeout=120)
        return dict(base, ok=bool(answer.get('ok')), message='signed in')
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        return dict(base, ok=False, message='%s (%s)' % (str(e)[:200], LOGIN_HELP[a]))
