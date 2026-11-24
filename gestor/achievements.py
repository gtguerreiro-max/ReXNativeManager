"""As conquistas (achievements) de cada jogo: a lista, os textos e os ícones vêm do SPA do título
(o recurso XDBF que todo o jogo traz, lido da imagem carregada que o `rexnative project` despeja em
run/image.bin, já desencriptada); as desbloqueadas vêm do que o SDK do ReXGlue grava quando o jogo
as dá (XGIUserWriteAchievements): <jogo>/userdata/achievements/<TitleID>.toml, com
`[unlocked.<id>] filetime = N`, no PC e no Deck.

O SDK desenha a notificação no seu overlay, que o renderizador nativo não mostra: sem isto, as
conquistas ficavam guardadas sem ninguém as ver."""
import datetime
import glob
import hashlib
import json
import os
import re
import struct
import threading

from . import config, fsutil

XACH = 0x58414348  # 'XACH': a tabela das conquistas
SEC_META, SEC_IMAGE, SEC_STRING = 1, 2, 3
ENGLISH = 1
SHOW_UNACHIEVED = 0x8  # sem isto, uma conquista secreta: nome e texto só depois de desbloqueada
_lock = threading.Lock()
_cache = {}  # work -> (mtime of image.bin, parsed)


def _xdbf_blocks(b):
    """Cada base XDBF da imagem: (início, {(secção, id): (início dos dados, tamanho)})."""
    i = b.find(b'XDBF')
    while i >= 0:
        try:
            _, cap, used, free_cap, _ = struct.unpack('>IIIII', b[i + 4:i + 24])
        except struct.error:
            return
        if 0 < used <= cap < 65536 and free_cap < 65536:
            data = i + 24 + cap * 18 + free_cap * 8
            entries = {}
            for k in range(used):
                o = i + 24 + 18 * k
                sec, eid, off, size = struct.unpack('>HQII', b[o:o + 18])
                if data + off + size <= len(b):
                    entries[(sec, eid)] = (data + off, size)
            yield i, entries
        i = b.find(b'XDBF', i + 4)


def _strings(b, loc):
    """Uma tabela de textos (XSTR) -> {id: texto}."""
    s, _ = loc
    if b[s:s + 4] != b'XSTR':
        return {}
    out = {}
    o = s + 14
    for _ in range(struct.unpack('>H', b[s + 12:s + 14])[0]):
        sid, n = struct.unpack('>HH', b[o:o + 4])
        out[sid] = b[o + 4:o + 4 + n].decode('utf-8', 'replace')
        o += 4 + n
    return out


def parse_image(path):
    """As conquistas do SPA numa imagem despejada: {'title', 'items': [...], 'images': {id: (início,
    tamanho)}}; None se não há nenhuma tabela de conquistas."""
    b = open(path, 'rb').read()
    for _, entries in _xdbf_blocks(b):
        loc = entries.get((SEC_META, XACH))
        if not loc:
            continue
        s, _ = loc
        if b[s:s + 4] != b'XACH':
            continue
        count = struct.unpack('>H', b[s + 12:s + 14])[0]
        text = entries.get((SEC_STRING, ENGLISH))
        strings = _strings(b, text) if text else {}
        if not strings:  # sem inglês: a primeira língua que houver
            for (sec, eid), l in sorted(entries.items()):
                if sec == SEC_STRING:
                    strings = _strings(b, l)
                    if strings:
                        break
        def text(sid):
            t = strings.get(sid, '')
            return '' if t.startswith('<String Placeholder') else t
        items = []
        for k in range(count):
            o = s + 14 + 0x24 * k
            aid, label, desc, unach, image, score, _, flags = struct.unpack('>HHHHIHHI', b[o:o + 20])
            items.append({'id': aid, 'name': text(label), 'description': text(desc),
                          'locked_text': text(unach), 'image': image, 'gamerscore': score,
                          'secret': not (flags & SHOW_UNACHIEVED)})
        images = {eid: l for (sec, eid), l in entries.items() if sec == SEC_IMAGE}
        return {'title': strings.get(0x8000), 'items': items, 'images': images}
    return None


def _image_path(work):
    return os.path.join(work, 'run', 'image.bin')


def _disk_cache(work):
    key = hashlib.sha1(os.path.normcase(os.path.abspath(work)).encode('utf-8')).hexdigest()[:16]
    return config.data_dir('achievements', 'lists', key + '.json')


def catalogue(work):
    """As conquistas de um jogo; None sem image.bin ou SPA. Em memória e num ficheiro pequeno por jogo
    (ler o image.bin são 50 a 400 MB), enquanto o image.bin não mudar."""
    p = _image_path(work)
    try:
        st = os.stat(p)
    except OSError:
        return None
    sig = [st.st_mtime, st.st_size]
    with _lock:
        hit = _cache.get(work)
        if hit and hit[0] == sig:
            return hit[1]
    parsed = None
    cache = _disk_cache(work)
    try:
        with open(cache, encoding='utf-8') as f:
            d = json.load(f)
        if d.get('sig') == sig:
            parsed = d['data']
            if parsed:
                parsed['images'] = {int(k): tuple(v) for k, v in parsed['images'].items()}
    except (OSError, ValueError, KeyError, AttributeError):
        parsed = None
    if parsed is None:
        try:
            parsed = parse_image(p)
        except (OSError, struct.error, ValueError):
            parsed = None
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            fsutil.write_text(cache, json.dumps({'sig': sig, 'work': work, 'data': parsed}))
        except OSError:
            pass
        if parsed is None:
            parsed = False  # sem conquistas: não se volta a ler a imagem
    with _lock:
        _cache[work] = (sig, parsed)
    return parsed or None


def icon(work, image_id):
    """Os bytes PNG do ícone de uma conquista (ou do jogo), ou None."""
    cat = catalogue(work)
    if not cat:
        return None
    loc = cat['images'].get(int(image_id))
    if not loc:
        return None
    with open(_image_path(work), 'rb') as f:
        f.seek(loc[0])
        data = f.read(loc[1])
    return data if data[:8] == b'\x89PNG\r\n\x1a\n' else None


UNLOCK_RE = re.compile(r'^\s*\[unlocked\.(\d+)\]\s*$')
TIME_RE = re.compile(r'^\s*filetime\s*=\s*(\d+)')


def parse_unlocks(text):
    """O ficheiro do SDK -> {id: data ISO (hora local) ou None}."""
    out, cur = {}, None
    for line in (text or '').splitlines():
        m = UNLOCK_RE.match(line)
        if m:
            cur = int(m.group(1))
            out[cur] = None
            continue
        m = TIME_RE.match(line)
        if m and cur is not None:
            out[cur] = filetime_iso(int(m.group(1)))
    return out


def filetime_iso(ft):
    """FILETIME do Windows (centenas de ns desde 1601) -> ISO na hora local."""
    if not ft:
        return None
    try:
        t = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(microseconds=ft // 10)
        return t.astimezone().replace(tzinfo=None).isoformat(timespec='seconds')
    except (OverflowError, ValueError):
        return None


def pc_unlocks(work):
    """As desbloqueadas a jogar no PC (run/userdata/achievements/*.toml)."""
    out = {}
    for p in glob.glob(os.path.join(work, 'run', 'userdata', 'achievements', '*.toml')):
        try:
            with open(p, encoding='utf-8', errors='replace') as f:
                out.update(parse_unlocks(f.read()))
        except OSError:
            continue
    return out


# -- as do Deck: o PC guarda as que viu (o Deck pode estar a dormir quando se abre a página) -----
def _deck_path():
    return config.data_dir('achievements', 'deck.json')


_seen = {'sig': None, 'data': {}}


def deck_seen():
    p = _deck_path()
    try:
        st = os.stat(p)
    except OSError:
        return {}
    sig = (st.st_mtime, st.st_size)
    if _seen['sig'] != sig:
        try:
            with open(p, encoding='utf-8') as f:
                _seen.update(sig=sig, data=json.load(f))
        except (OSError, ValueError):
            return {}
    return json.loads(json.dumps(_seen['data']))  # uma cópia: quem a recebe pode mexer-lhe


def record_deck(per_game):
    """per_game: {slug: {id: iso}} lido do Deck agora. Junta ao que já se sabia (uma conquista nunca
    desaparece só porque um ficheiro não se leu) e devolve as novas: [(slug, id, iso)]."""
    with _lock:
        seen = deck_seen()
        new = []
        for slug, unl in per_game.items():
            have = seen.setdefault(slug, {})
            for aid, when in unl.items():
                k = str(aid)
                if k not in have:
                    new.append((slug, int(aid), when))
                have[k] = when or have.get(k)
        if new or not os.path.exists(_deck_path()):
            os.makedirs(os.path.dirname(_deck_path()), exist_ok=True)
            fsutil.write_text(_deck_path(), json.dumps(seen, indent=1))
        return new


def from_listing(data):
    """A listagem do Deck traz, por jogo, o ficheiro do SDK lido lá ({id: filetime})."""
    per = {}
    for g in data.get('games') or []:
        a = g.get('achievements')
        if isinstance(a, dict):
            per[g['slug']] = {int(k): filetime_iso(int(v or 0)) for k, v in a.items() if str(k).isdigit()}
    return record_deck(per) if per else []


def recent(works, limit=8):
    """As últimas desbloqueadas no Deck, de todos os jogos (as mais novas primeiro). works: {slug: work}."""
    out = []
    for slug, unl in deck_seen().items():
        work = works.get(slug)
        cat = catalogue(work) if work else None
        if not cat:
            continue
        by_id = {a['id']: a for a in cat['items']}
        for k, when in unl.items():
            a = by_id.get(int(k))
            if a:
                out.append({'slug': slug, 'id': a['id'], 'name': a['name'], 'gamerscore': a['gamerscore'],
                            'image': a['image'], 'when': when, 'title': cat.get('title') or slug})
    out.sort(key=lambda x: x['when'] or '', reverse=True)
    return out[:limit]


def view(work, slug):
    """A lista para mostrar: cada conquista com unlocked (data) e onde (deck/pc), e os totais."""
    cat = catalogue(work)
    if not cat:
        return None
    deck = {int(k): v for k, v in (deck_seen().get(slug) or {}).items()}
    pc = pc_unlocks(work)
    items, score, got_score = [], 0, 0
    for a in cat['items']:
        where = [w for w, d in (('deck', deck), ('pc', pc)) if a['id'] in d]
        when = max((d[a['id']] or '' for d in (deck, pc) if a['id'] in d), default='') or None
        unlocked = bool(where)
        score += a['gamerscore']
        got_score += a['gamerscore'] if unlocked else 0
        hide = a['secret'] and not unlocked
        items.append({'id': a['id'], 'gamerscore': a['gamerscore'], 'image': None if hide else a['image'],
                      'secret': a['secret'],
                      'name': 'Secret achievement' if hide else a['name'],
                      'description': (a['description'] if unlocked else a['locked_text'] or a['description'])
                      if not hide else 'Keep playing to find out.',
                      'unlocked': unlocked, 'when': when, 'where': where})
    items.sort(key=lambda x: (not x['unlocked'], x['when'] and -_ts(x['when']) or 0, x['id']))
    return {'count': len(items), 'unlocked': sum(1 for x in items if x['unlocked']),
            'gamerscore': score, 'got_score': got_score, 'items': items}


def summary(work, slug):
    """Só os números (para listas de jogos), sem os textos."""
    v = view(work, slug)
    if not v:
        return None
    return {k: v[k] for k in ('count', 'unlocked', 'gamerscore', 'got_score')}


def _ts(iso):
    try:
        return datetime.datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return 0


# XLanguage (the SDK's kernel.user_language): what each id is called, in its own language.
LANGUAGES = {1: 'English', 2: '日本語', 3: 'Deutsch', 4: 'Français', 5: 'Español', 6: 'Italiano',
             7: '한국어', 8: '繁體中文', 9: 'Português', 10: '简体中文', 11: 'Polski', 12: 'Русский',
             13: 'Svenska', 14: 'Türkçe', 15: 'Norsk', 16: 'Nederlands', 17: '简体中文'}
_langs = {}  # work -> (mtime of image.bin, [ids])


def languages(work):
    """The languages the game plays in (XLanguage ids, English first), [] when the game has no
    image yet: those its SPA has texts in (a title localises its achievements into the languages
    it is made in) that its data carries (data_languages), English always."""
    img = os.path.join(work, 'run', 'image.bin')
    try:
        mtime = os.path.getmtime(img)
    except OSError:
        return []
    hit = _langs.get(work)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        b = open(img, 'rb').read()
    except OSError:
        return []
    best = []
    for _, entries in _xdbf_blocks(b):
        ids = sorted(eid for (sec, eid) in entries if sec == SEC_STRING and eid in LANGUAGES)
        if len(ids) > len(best):
            best = ids
    # 10 is the SDK's old simplified Chinese id, kept beside 17: one entry.
    if 10 in best and 17 in best:
        best.remove(10)
    game = os.path.join(work, 'run', 'game')
    data = data_languages(game) if os.path.isdir(game) else None
    if data is not None:
        best = [i for i in best if i in data or i == 1]
    _langs[work] = (mtime, best)
    return best

# -- the languages the game's data carries ----------------------------------------------------------
# A title's SPA lists every language the title was made in, across its regions; a disc can carry
# fewer (Diablo III's European disc: enGB and frFR packs only; Burnout Crash's: EN-US.LANG and
# FR-FR.LANG), and a language it lacks plays in English. Files and folders named by locale, as
# siblings that differ only in it (enGB_Act1.cpk, frFR_Act1.cpk; data/language/pl-pl), say which:
# speech, Kinect grammars, voices and subtitles left out (Forza Horizon's SatNav voices, Babel
# Rising's Kinect grammars are not its text).
_LOCALE_PAIRS = {
    'en': 'US GB UK AU CA IE NZ', 'fr': 'FR CA BE CH', 'de': 'DE AT CH', 'es': 'ES MX AR CL CO',
    'it': 'IT CH', 'pt': 'PT BR', 'ja': 'JP', 'ko': 'KR', 'zh': 'TW HK CN SG CHT CHS HANT HANS', 'pl': 'PL', 'ru': 'RU',
    'sv': 'SE', 'tr': 'TR', 'nb': 'NO', 'no': 'NO', 'nl': 'NL BE', 'cs': 'CZ', 'hu': 'HU', 'da': 'DK',
    'fi': 'FI', 'el': 'GR'}
_LOCALE_IDS = {'en': [1], 'ja': [2], 'de': [3], 'fr': [4], 'es': [5], 'it': [6], 'ko': [7], 'pt': [9],
               'pl': [11], 'ru': [12], 'sv': [13], 'tr': [14], 'nb': [15], 'no': [15], 'nl': [16]}
_LOCALE_WORDS = {'english': [1], 'japanese': [2], 'german': [3], 'deutsch': [3], 'french': [4],
                 'francais': [4], 'spanish': [5], 'espanol': [5], 'italian': [6], 'italiano': [6],
                 'korean': [7], 'chinese': [8, 10, 17], 'portuguese': [9], 'portugues': [9], 'brazilian': [9],
                 'polish': [11], 'russian': [12], 'swedish': [13], 'turkish': [14], 'norwegian': [15],
                 'dutch': [16]}
_LOCALE_TOKEN = re.compile(r'(?<![A-Za-z])([A-Za-z]{2})([-_]?)([A-Za-z]{2}|cht|chs|hant|hans)(?![A-Za-z])',
                           re.I)
_LOCALE_WORD = re.compile(r'(?i)(?<![A-Za-z])(%s)(?![A-Za-z])' % '|'.join(_LOCALE_WORDS))
_NOT_TEXT = re.compile(r'(?i)speech|kinect|grammar|satnav|voice|audio|sound|sfx|music|movie|video|subt'
                       r'|(?<![a-z])vo(?![a-z])')


def _locales_in(name):
    """[(language key, (start, end))] of the locale tokens and language words in a file name."""
    out = []
    for m in _LOCALE_TOKEN.finditer(name):
        lang, sep, country = m.group(1), m.group(2), m.group(3)
        if lang.lower() not in _LOCALE_PAIRS or country.upper() not in _LOCALE_PAIRS[lang.lower()].split():
            continue
        if not sep and not (lang.islower() and country.isupper() and len(country) == 2):
            continue  # enGB, not a word's four letters
        if lang.lower() == 'zh' and country.upper() in ('CN', 'SG', 'CHS', 'HANS'):
            ids = [10, 17]
        elif lang.lower() == 'zh':
            ids = [8]
        else:
            ids = _LOCALE_IDS.get(lang.lower(), [])
        out.append((lang.lower(), ids, m.span()))
    for m in _LOCALE_WORD.finditer(name):
        out.append((m.group(1).lower(), _LOCALE_WORDS[m.group(1).lower()], m.span()))
    return out


def data_languages(game_dir, limit=40000):
    """The XLanguage ids of the language packs in a game's data (its folder of files), or None
    when its names show no set of them (one language alone says nothing)."""
    groups = {}
    seen = 0
    for dp, dn, fn in os.walk(game_dir):
        rel = os.path.relpath(dp, game_dir)
        if rel.count(os.sep) >= 5:
            dn[:] = []
        for name in dn + fn:
            seen += 1
            found = _locales_in(name)
            if len(found) != 1:
                continue
            key, ids, (a, b) = found[0]
            if _NOT_TEXT.search(rel) or _NOT_TEXT.search(name[:a] + name[b:]):
                continue
            g = groups.setdefault((rel, name[:a].lower() + '\0' + name[b:].lower()), {})
            g[key] = ids
        if seen > limit:
            break
    if not any(len(g) >= 2 for g in groups.values()):
        return None
    out = set()
    for g in groups.values():
        for ids in g.values():
            out.update(ids)
    return out
