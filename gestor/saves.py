"""Os saves da cópia do jogo no PC: run/userdata/<perfil>/<jogo>/00000001 e os seus cabeçalhos
(Headers/00000001), como o ReXGlue os escreve (no Deck é igual, ao lado do jogo).

Um relatório do Deck pode trazer os saves do jogador para a cópia do PC: sem eles, o Claude não
chega a um menu que só abre com o progresso do jogo (Asura's Wrath: o menu dos episódios). Os saves
que o PC tinha ficam antes numa cópia em <data_dir>/backups/pc. Os envios para o Deck nunca levam
userdata/, por isso os saves do Deck não mudam."""
import datetime
import glob
import os
import re
import shutil
import tarfile

from . import config

# <perfil>/<jogo>/00000001 (os saves) e <perfil>/<jogo>/Headers/00000001 (os seus cabeçalhos).
PATTERNS = (('*', '*', '00000001'), ('*', '*', 'Headers', '00000001'))
MEMBER = re.compile(r'^userdata/[0-9A-Fa-f]{16}/[0-9A-Fa-f]{8}/(Headers/)?00000001(/[^/]+)*$')


def dirs(work):
    """As pastas de saves da cópia do PC (caminhos absolutos)."""
    ud = os.path.join(work, 'run', 'userdata')
    return sorted(p for pat in PATTERNS for p in glob.glob(os.path.join(ud, *pat)) if os.path.isdir(p))


def backup(work, slug):
    """Os saves da cópia do PC num .tar em <data_dir>/backups/pc; None se não houver nenhum."""
    found = dirs(work)
    if not found:
        return None
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    dest = os.path.join(config.data_dir('backups', 'pc'), '%s-%s.tar' % (slug, stamp))
    part = dest + '.part'
    run = os.path.join(work, 'run')
    try:
        with tarfile.open(part, 'w') as t:
            for d in found:
                t.add(d, arcname=os.path.relpath(d, run).replace(os.sep, '/'))
        with tarfile.open(part) as t:
            t.getmembers()
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return dest


def install(work, slug, tar_path):
    """Põe os saves de um .tar (os do Deck) na cópia do PC, no lugar dos que lá estavam para os
    mesmos jogos (guardados antes em backups/pc). Devolve {'backup', 'files', 'run'}."""
    with tarfile.open(tar_path) as t:
        members = t.getmembers()
    titles = set()
    for m in members:
        name = m.name.rstrip('/')
        if not MEMBER.match(name) or '..' in name.split('/') or not (m.isfile() or m.isdir()):
            raise RuntimeError('the saves have an unexpected entry: %s' % m.name)
        titles.add(tuple(name.split('/')[1:3]))
    files = sum(1 for m in members if m.isfile())
    if not files:
        raise RuntimeError('the saves are empty')
    run = os.path.join(work, 'run')
    old = backup(work, slug)
    for profile, title in titles:
        for sub in (('00000001',), ('Headers', '00000001')):
            p = os.path.join(run, 'userdata', profile, title, *sub)
            if os.path.isdir(p):
                shutil.rmtree(p)
    with tarfile.open(tar_path) as t:
        t.extractall(run, filter='data')
    return {'backup': old, 'files': files, 'run': os.path.join(run, 'userdata')}
