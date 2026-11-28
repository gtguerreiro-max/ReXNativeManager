"""What a prepared game no longer needs, removed once it is prepared and built (keep_archives off,
the default; the Deck's Sem PC mode does the same, rexdeck.disk.tidy): the archive the app
downloaded for it (in the downloads folder only) and archive/, that archive extracted in the game's
folder, with the staging folders a stopped run left there (archive.part, game-data.part).

Only extraction reads them (ReXNative's prepare.stage_game): Prepare again and the Claude fixes run
`rexnative prepare` over game-data as it is, without the archive. When game-data is not complete
either, the archive is downloaded again first (app.game_pipeline, orders.order_job), as an order
does. The user's own files (Add your own game, Your files) are never touched: only their extracted
copy in archive/, which the app made."""
import glob
import os
import shutil
import stat

from . import config, games

PARTS = ('archive.part', 'archive.part-*', 'game-data.part', 'game-data.part-*')


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def _inside(path, root):
    p, r = _norm(path), _norm(root)
    return p != r and p.startswith(r.rstrip('\\/') + os.sep)


def game_complete(work):
    """game-data has the game's executable (prepare.entry_xex: a disc's DEFAULT.XEX, a package's
    Default.xex)."""
    try:
        return any(f.lower() == 'default.xex' and os.path.isfile(os.path.join(work, 'game-data', f))
                   for f in os.listdir(os.path.join(work, 'game-data')))
    except OSError:
        return False


def built(work):
    name = games.exe_name(work)
    return bool(name) and os.path.isfile(os.path.join(work, 'run', name + '.exe'))


def extracted(work):
    """archive/ holds the archive extracted (prepare goes on from it without the archive)."""
    d = os.path.join(work, 'archive')
    try:
        return os.path.isdir(d) and bool(os.listdir(d))
    except OSError:
        return False


def prepare_needs_source(work, source):
    """Whether `rexnative prepare` would have to read the source, which is not there: no complete
    game-data and no archive/ to go on from."""
    return not (source and os.path.exists(source)) and not game_complete(work) and not extracted(work)


def downloaded(source):
    """The source when the app downloaded it (a file in the downloads folder, and in none of the
    user's own folders), else None."""
    cfg = config.load()
    if not source or not os.path.isfile(source) or not _inside(source, cfg['download_dir']):
        return None
    if any(_inside(source, d) or _norm(source) == _norm(d) for d in cfg.get('own_dirs') or [] if d):
        return None
    return source


def download_of(source):
    """(item, name) of a source in the downloads folder (<download_dir>/<item>/<name>), there or
    not, for downloading it again; None for one of the user's own files."""
    cfg = config.load()
    if not source or not _inside(source, cfg['download_dir']):
        return None
    rel = os.path.relpath(os.path.abspath(source), os.path.abspath(cfg['download_dir']))
    parts = rel.split(os.sep)
    return (parts[0], parts[1]) if len(parts) == 2 else None


def size_of(path):
    """Bytes under path, without following links or junctions."""
    if os.path.isfile(path):
        return os.path.getsize(path)
    total, stack = 0, [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_symlink() or (hasattr(os.path, 'isjunction') and os.path.isjunction(e.path)):
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def _rmtree(path):
    """shutil.rmtree that also removes read-only files (a RAR's), and never follows a junction."""
    def retry(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    try:
        shutil.rmtree(path, onexc=retry)
    except TypeError:  # Python before 3.12
        shutil.rmtree(path, onerror=retry)


def targets(work, source):
    """What goes: archive/, the staging folders, and the downloaded archive."""
    out = [p for p in [os.path.join(work, 'archive')] if os.path.isdir(p)]
    for pat in PARTS:
        out += [p for p in glob.glob(os.path.join(glob.escape(work), pat)) if p not in out]
    src = downloaded(source)
    if src:
        out.append(src)
    return out


def _amount(n):
    return '%.1f GB' % (n / 1e9) if n >= 1e9 else '%.0f MB' % (n / 1e6)


def after_prepare(job, work, source):
    """After a prepare that succeeded: removes what the game no longer needs, unless keep_archives
    is on or the game is not complete and built. Returns a line for the step's summary ('' when
    nothing went). An archive another job is downloading again stays."""
    if config.load().get('keep_archives') or not game_complete(work) or not built(work):
        return ''
    busy = set()
    manager = getattr(job, 'manager', None)
    if manager is not None:
        for j in manager.active(kind='download'):
            p = j.params or {}
            if p.get('item') and p.get('name'):
                busy.add(_norm(os.path.join(config.load()['download_dir'], p['item'], p['name'])))
    freed, gone = 0, []
    for t in targets(work, source):
        if _norm(t) in busy:
            continue
        n = size_of(t)
        try:
            if os.path.isdir(t) and not os.path.islink(t):
                _rmtree(t)
            else:
                os.remove(t)
        except OSError as e:
            job.log('could not remove %s: %s' % (t, e))
            continue
        freed += n
        gone.append(os.path.basename(t) if os.path.dirname(t) == work else t)
    if not gone:
        return ''
    job.event('info', 'Removed what the game no longer needs (%s): %s. Settings > Keep downloaded '
                      'archives keeps them.' % (_amount(freed), ', '.join(gone)))
    return '; archive removed (%s freed)' % _amount(freed)
