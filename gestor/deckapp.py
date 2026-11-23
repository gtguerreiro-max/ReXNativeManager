"""O Gestor no Steam Deck: um atalho na biblioteca do Steam ("Gestor ReXNative") que abre o Modo
Deck desta app (/deck) em ecrã inteiro, num Firefox só dele (o flatpak que o Deck já tem).

Instalar (Definições > Modo Deck) liga a app à rede de casa, cria o token do Deck e escreve-o lá
por SSH (nada a escrever no Deck), envia o lançador (deckkit/) para
~/.local/share/gestor-rexnative e põe o atalho, com arte própria, no Steam (fechado uma vez)."""
import io
import os
import posixpath
import tarfile
import time

from . import config, deck, lan, state

NAME = 'Gestor ReXNative'
DIR = '.local/share/gestor-rexnative'  # na pasta do utilizador deck
KIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deckkit')
VERSION = 4  # o lançador (deckkit/): sobe quando os ficheiros mudam; a app avisa o Deck que tem um antigo
# 3: o modo (PC, Sem PC, Automático) no ficheiro mode, ao lado do gestor.conf

GREEN = (95, 191, 63)
FONTS = r'C:\Windows\Fonts'


# -- arte do atalho -------------------------------------------------------------------------------
def _font(size, weight='black'):
    from PIL import ImageFont
    names = {'black': ('seguibl.ttf', 'segoeuib.ttf'), 'bold': ('segoeuib.ttf',),
             'semi': ('seguisb.ttf', 'segoeuib.ttf'), 'light': ('segoeuil.ttf', 'segoeui.ttf')}[weight]
    for n in names:
        p = os.path.join(FONTS, n)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _background(w, h, cards=True, seed=7):
    """Fundo escuro com um brilho verde e capas de jogos inclinadas, desfocadas, ao fundo."""
    import random
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(seed)
    im = Image.new('RGB', (w, h), (11, 14, 16))
    glow = Image.new('L', (w, h), 0)
    gd = ImageDraw.Draw(glow)
    r = int(max(w, h) * 0.55)
    cx, cy = int(w * 0.72), int(h * 0.18)
    gd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=140)
    glow = glow.filter(ImageFilter.GaussianBlur(max(w, h) // 5))
    im.paste(Image.new('RGB', (w, h), (24, 70, 32)), (0, 0), glow)
    if cards:
        layer = Image.new('RGBA', (w * 2, h * 2), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        cw = int(min(w, h) * 0.34)
        ch = int(cw * 1.4)
        for row in range(-1, int(h * 2 / ch) + 2):
            for col in range(-1, int(w * 2 / cw) + 2):
                x = col * (cw + cw // 6) + (row % 2) * cw // 2
                y = row * (ch + cw // 6)
                shade = rnd.randint(22, 40)
                tint = (shade, shade + rnd.randint(6, 22), shade + 4, 255)
                ld.rounded_rectangle((x, y, x + cw, y + ch), radius=cw // 12, fill=tint)
                if rnd.random() < 0.18:
                    ld.rounded_rectangle((x, y, x + cw, y + ch), radius=cw // 12,
                                         outline=GREEN + (200,), width=max(2, cw // 40))
        layer = layer.rotate(-14, resample=Image.BICUBIC, expand=False)
        layer = layer.crop((w // 2, h // 2, w // 2 + w, h // 2 + h))
        layer = layer.filter(ImageFilter.GaussianBlur(max(1, min(w, h) // 260)))
        fade = Image.linear_gradient('L').resize((w, h)).point(lambda v: int(v * 0.55))
        im.paste(layer.convert('RGB'), (0, 0), Image.composite(layer.split()[3], Image.new('L', (w, h), 0), fade))
    shade = Image.linear_gradient('L').resize((w, h)).point(lambda v: int(255 - v * 0.45))
    dark = Image.new('RGB', (w, h), (6, 8, 9))
    im = Image.composite(im, dark, shade)
    return im


def _wordmark(draw, x, y, size, anchor='la'):
    """"Gestor" por cima, "ReXNative" com o X verde."""
    small = _font(int(size * 0.34), 'semi')
    big = _font(size, 'black')
    draw.text((x, y), 'GESTOR', font=small, fill=(170, 182, 190), anchor=anchor)
    yb = y + int(size * 0.42)
    parts = [('Re', (240, 244, 246)), ('X', GREEN), ('Native', (240, 244, 246))]
    total = sum(draw.textlength(t, font=big) for t, _ in parts)
    if anchor[0] == 'm':
        x = x - total / 2
    for t, c in parts:
        draw.text((x, yb), t, font=big, fill=c, anchor='l' + anchor[1])
        x += draw.textlength(t, font=big)


def make_art(dest):
    """portrait.png 600x900, grid.png 920x430, hero.png 1920x620, logo.png e icon.png em dest."""
    from PIL import Image, ImageDraw
    os.makedirs(dest, exist_ok=True)
    im = _background(600, 900)
    d = ImageDraw.Draw(im)
    _wordmark(d, 300, 610, 108, anchor='ma')
    d.text((300, 820), 'your Xbox 360 games, native', font=_font(26, 'light'),
           fill=(150, 162, 170), anchor='ma')
    im.save(os.path.join(dest, 'portrait.png'))
    im = _background(920, 430, seed=11)
    d = ImageDraw.Draw(im)
    _wordmark(d, 60, 140, 112)
    im.save(os.path.join(dest, 'grid.png'))
    _background(1920, 620, seed=13).save(os.path.join(dest, 'hero.png'))
    logo = Image.new('RGBA', (1000, 300), (0, 0, 0, 0))
    _wordmark(ImageDraw.Draw(logo), 500, 40, 170, anchor='ma')
    logo.save(os.path.join(dest, 'logo.png'))
    icon = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    idr = ImageDraw.Draw(icon)
    idr.rounded_rectangle((8, 8, 248, 248), radius=52, fill=(16, 22, 24, 255), outline=GREEN + (255,), width=10)
    idr.text((128, 134), 'X', font=_font(170, 'black'), fill=GREEN, anchor='mm')
    icon.save(os.path.join(dest, 'icon.png'))
    return dest


# -- instalar ------------------------------------------------------------------------------------
def _files(conf_text, art_dir, kit_py):
    """(caminho no tar, bytes, modo) dos ficheiros do Gestor no Deck."""
    out = []
    for n, mode in (('gestor.sh', 0o755), ('start.html', 0o644), ('user.js', 0o644)):
        data = open(os.path.join(KIT, n), 'rb').read().replace(b'\r\n', b'\n')
        out.append((n, data, mode))
    out.append(('gestor.conf', conf_text.encode('utf-8'), 0o600))
    out.append(('steam_shortcuts.py', open(kit_py, 'rb').read(), 0o755))
    out.append(('VERSION', str(VERSION).encode(), 0o644))
    for n in sorted(os.listdir(art_dir)):
        out.append(('art/' + n, open(os.path.join(art_dir, n), 'rb').read(), 0o644))
    return out


def _tar(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.GNU_FORMAT) as t:
        for name, data, mode in files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = mode
            info.mtime = int(time.time())
            info.uid = info.gid = 1000
            info.uname = info.gname = 'deck'
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def status():
    g = state.get('deck', 'gestor') or {}
    return dict(g, name=NAME)


def install_job(job, servers):
    cfg = config.load()
    dk = deck.Deck()
    ok, err = dk.reachable(tries=3)
    if not ok:
        raise RuntimeError('The Deck is not responding (%s)' % err)
    job.event('step', 'Checking the Deck: Firefox and where the Manager goes')
    r = dk.ssh('flatpak info org.mozilla.firefox >/dev/null 2>&1 && echo firefox; echo "home=$HOME"', timeout=60)
    if 'firefox' not in r.stdout:
        raise RuntimeError('The Deck does not have Firefox: install it from the store (Discover, in '
                           'Desktop Mode) and try again')
    home = next((l[5:] for l in r.stdout.splitlines() if l.startswith('home=')), '/home/deck').strip()
    gdir = posixpath.join(home, DIR)

    # A app na rede de casa.
    if not cfg.get('lan_enabled'):
        config.save({'lan_enabled': True})
        job.event('info', 'The app now accepts connections from the home network (only from paired devices)')
    servers.refresh()
    for _ in range(20):
        if servers.running:
            break
        time.sleep(0.5)
    if not servers.running:
        raise RuntimeError('The app could not open port %d on the network: %s' % (
            cfg['port'], servers.error or 'no private network address'))

    # O Deck chega cá? (a firewall do Windows pode bloquear o Python)
    urls = lan.urls()
    probe = ' '.join('curl -s -m 4 %s/api/ping >/dev/null && echo "ok %s";' % (deck.q(u), u) for u in urls)
    r = dk.ssh(probe + ' true', timeout=60)
    good = [l[3:].strip() for l in r.stdout.splitlines() if l.startswith('ok ')]
    if not good:
        raise RuntimeError('The Deck cannot reach the app at %s: Windows Firewall may be blocking '
                           'Python on port %d (allow it on private networks)' % (
                               ', '.join(urls), cfg['port']))
    job.event('ok', 'The Deck reaches the app at %s' % ', '.join(good))
    urls = good + [u for u in urls if u not in good]

    # O token deste Deck: o que já lá está, se ainda valer (o Gestor aberto e o plugin continuam a
    # funcionar); senão um novo, e o anterior deixa de valer.
    old = dk.ssh('cat %s 2>/dev/null' % deck.q(posixpath.join(gdir, 'gestor.conf')), timeout=30).stdout
    token = next((l.split('=', 1)[1].strip().strip('"') for l in old.splitlines()
                  if l.startswith('TOKEN=')), None)
    dev = lan.check(token) if token else None
    if dev:
        dev_id = dev['id']
    else:
        lan.revoke_kind('deck')
        dev_id, token = lan.new_device('Steam Deck', 'deck')

    art = make_art(config.data_dir('deckapp', 'art'))
    kit_py = os.path.join(cfg['rexnative_dir'], 'deck', 'steam_shortcuts.py')
    if not os.path.exists(kit_py):
        raise RuntimeError('%s not found' % kit_py)
    conf = '# ReXNative Manager: written by the PC app (Settings > Deck Mode)\nURLS="%s"\nTOKEN="%s"\n' % (
        ' '.join(urls), token)
    data = _tar(_files(conf, art, kit_py))
    job.event('step', 'Sending the Manager to %s' % gdir)
    r = dk.ssh('mkdir -p %s && tar -xf - -C %s && echo "files sent"' % (deck.q(gdir), deck.q(gdir)),
               input_bytes=data, timeout=120)
    if 'files sent' not in r.stdout:
        raise RuntimeError('the transfer failed: %s' % (r.stderr or r.stdout)[-300:])
    # Um Deck que estava no modo Sem PC (instalado sem PC) passa a Automático: o PC quando está
    # ligado, o próprio Deck quando não.
    r = dk.ssh('m=%s/mode; if [ "$(cat "$m" 2>/dev/null)" = local ]; then echo auto > "$m"; echo now-auto; fi'
               % deck.q(gdir), timeout=30)
    if 'now-auto' in r.stdout:
        job.event('info', 'This Deck was set to work without the PC: it is now Automatic (the PC when it '
                          'answers, the Deck when not)')

    # O atalho no Steam (fechado uma vez), se ainda não houver.
    listing = dk.listing(light=True)
    sc = next((s for s in listing['shortcuts'] if s['name'] == NAME), None)
    if sc:
        job.event('info', 'The shortcut is already in the library: only the files were updated')
    else:
        b = deck.busy(dk)
        t0 = time.time()
        if b:
            job.event('info', 'You are playing on the Deck: the shortcut is added when you quit the game')
        while b:
            if time.time() - t0 > 1800:
                raise RuntimeError('The Deck was busy for 30 min: the Manager is there, but the shortcut '
                                   'is missing (install again when you are not playing)')
            job.sleep(30)
            b = deck.busy(dk)
        job.event('step', 'Adding "%s" to the library (Steam closes and reopens once)' % NAME)
        body = 'python3 %s add %s %s --start-dir %s --art-dir %s\necho "shortcut created"\n' % (
            deck.q(posixpath.join(gdir, 'steam_shortcuts.py')), deck.q(NAME),
            deck.q(posixpath.join(gdir, 'gestor.sh')), deck.q(gdir), deck.q(posixpath.join(gdir, 'art')))
        r = dk.ssh('bash -s', input_text=deck.STEAM_HEAD + body, timeout=400)
        job.log((r.stdout + r.stderr).strip())
        if r.returncode != 0 or 'shortcut created' not in r.stdout:
            raise RuntimeError('Steam did not accept the shortcut: %s' % (r.stdout + r.stderr)[-300:])
        listing = dk.listing(light=True)
        sc = next((s for s in listing['shortcuts'] if s['name'] == NAME), None)
    state.update('deck', 'gestor', {'appid': sc and sc['appid'], 'dir': gdir, 'at': time.time(),
                                    'device': dev_id, 'version': VERSION, 'urls': urls})
    deck.status(refresh=True)
    job.event('ok', '"%s" is in the Deck library (Non-Steam): open it in Game Mode and pick '
                    'games with the controller' % NAME)
    return {'appid': sc and sc['appid'], 'dir': gdir}
