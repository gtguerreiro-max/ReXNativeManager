"""Apagar um jogo deste PC: a pasta de trabalho (o jogo preparado e compilado, os saves e as
definições do PC) e, se se pedir, o arquivo descarregado. Antes, os saves do PC vão para
backups/pc (saves.backup). A cópia no Deck fica como está; os jogos teus (as tuas pastas de dumps,
os teus ficheiros) nunca são tocados: só o que a app descarregou para a pasta de downloads."""
import os
import shutil
import stat

from . import config, games, saves, scenes, state


def _amount(n):
    return '%.1f GB' % (n / 1e9) if n >= 1e9 else '%.0f MB' % (n / 1e6)


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def _inside(path, root):
    p, r = _norm(path), _norm(root)
    return p != r and p.startswith(r.rstrip('\\/') + os.sep)


def check_work(work):
    """A pasta é a de um jogo, dentro de uma das pastas de trabalho (nunca a própria raiz, nem
    outra coisa do PC); senão RuntimeError."""
    roots = config.load().get('work_roots') or [config.load()['work_dir']]
    if not work or not any(_inside(work, r) for r in roots):
        raise RuntimeError('%s is not a game folder inside the work folders' % work)
    if not os.path.isfile(os.path.join(work, 'prepare.json')):
        raise RuntimeError('%s has no prepare.json: not a prepared game folder' % work)
    return work


def download_of(work):
    """O arquivo descarregado de que o jogo foi preparado, se estiver na pasta de downloads da app
    (um jogo teu, de uma pasta tua, devolve None: esse nunca se apaga)."""
    src = games.info(work).get('source')
    if src and os.path.isfile(src) and _inside(src, config.load()['download_dir']):
        return src
    return None


def _is_link(p):
    return os.path.islink(p) or (hasattr(os.path, 'isjunction') and os.path.isjunction(p))


def size_of(path):
    """Bytes de uma pasta, sem seguir as ligações (run/game e run/title-update são junctions)."""
    total = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if _is_link(e.path):
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def disk(work):
    """O que apagar o jogo liberta e o que se guarda antes, para a janela de confirmação."""
    dl = download_of(work)
    return {'work': work, 'work_bytes': size_of(work), 'saves': len(saves.dirs(work)),
            'download': {'path': dl, 'bytes': os.path.getsize(dl)} if dl else None,
            'scenes': len(scenes.scenes(os.path.basename(work)))}


def _unlink_links(root):
    """Tira as ligações (junctions, symlinks) dentro da pasta antes de a apagar: apagar nunca segue
    para onde elas apontam."""
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            if _is_link(e.path):
                try:
                    os.rmdir(e.path)  # a junction or a directory symlink: the link alone goes
                except OSError:
                    os.unlink(e.path)
            elif e.is_dir(follow_symlinks=False):
                stack.append(e.path)


def _rmtree(path):
    def retry(func, p, _exc):  # um ficheiro só de leitura
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=retry)


def delete_job(job, work, slug, backup_saves=True, download=False):
    check_work(work)
    title = games.info(work).get('title') or slug
    freed = 0
    out = {'title': title}
    if backup_saves and saves.dirs(work):
        job.event('step', 'Keeping a copy of the saves of this PC')
        out['backup'] = saves.backup(work, slug)
        job.event('ok', 'The saves of this PC are in %s' % out['backup'])
    dl = download_of(work) if download else None
    job.event('step', 'Deleting %s' % work)
    size = size_of(work)
    _unlink_links(work)
    _rmtree(work)
    freed += size
    job.event('ok', 'The game folder is gone (%s)' % _amount(size))
    if dl:
        n = os.path.getsize(dl)
        os.remove(dl)
        freed += n
        try:
            os.rmdir(os.path.dirname(dl))  # a pasta do item, se ficou vazia
        except OSError:
            pass
        job.event('ok', 'The downloaded file is gone (%s): %s' % (_amount(n), dl))
        out['download'] = dl
    # O que a app guardava do jogo: o estado (testes, cenas, comparações) e as cenas de teste.
    state.remove('games', state.game_key(work))
    sd = scenes.root(slug)
    if os.path.isdir(sd):
        shutil.rmtree(sd, ignore_errors=True)
    out['freed'] = freed
    on_deck = any(g.get('slug') == slug for g in (state.get('deck', 'last') or {}).get('games') or [])
    job.event('ok', '%s is no longer on this PC: %s freed%s' % (
        title, _amount(freed), '; it stays on the Deck as it is' if on_deck else ''))
    return out
