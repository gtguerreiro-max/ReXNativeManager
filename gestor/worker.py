"""Trabalho que corre num processo à parte (para poder ser cancelado sem parar a app):

  python -m gestor.worker download ITEM NOME DESTINO TAMANHO MD5

Descarrega um ficheiro de um item do Internet Archive com a biblioteca internetarchive (que
retoma um ficheiro parcial e se autentica com as chaves S3 de ia.ini), e verifica o MD5."""
import hashlib
import os
import sys
import time


def fmt(n):
    return '%.2f GB' % (n / 1e9) if n >= 1e9 else '%.1f MB' % (n / 1e6)


def md5_of(path, log):
    h = hashlib.md5()
    size = os.path.getsize(path)
    done, shown = 0, 0
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
            done += len(chunk)
            if done - shown > max(size // 5, 1 << 30):
                shown = done
                log('  checking the MD5: %d%%' % (done * 100 // max(size, 1)))
    return h.hexdigest()


# A connection left slow (after the network went down and came back, the transfer goes on at a
# tenth of the speed and never recovers on its own). Measured over WINDOW seconds: a speed under
# SLOW_SHARE of the best this download had, or under SLOW_FLOOR, ends the request and a new one goes
# on from where it is (often to another of the Archive's servers). When a new connection is no
# faster HELPLESS times in a row, the line is just that slow and it stops trying.
WINDOW = 20
SLOW_SHARE = 0.3
SLOW_FLOOR = 0.6e6
HELPLESS = 3


class Slow(Exception):
    def __init__(self, rate, best):
        super().__init__('%.2f MB/s, it did %.2f MB/s' % (rate / 1e6, best / 1e6))
        self.rate = rate


def fetch(f, dest, size, state):
    """The rest of the file (a Range request from what is on disk), written as it arrives. Raises
    Slow when the connection got slow (the caller reconnects), anything else on errors."""
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    if have >= size:
        return
    r = f.item.session.get(f.url, headers={'Range': 'bytes=%d-' % have}, stream=True,
                           timeout=(30, 120), auth=getattr(f, 'auth', None))
    try:
        if r.status_code in (401, 403):
            raise PermissionError('%d %s' % (r.status_code, r.reason))
        r.raise_for_status()
        mode = 'ab'
        if r.status_code == 200 and have:  # the server sent the whole file: start again
            mode = 'wb'
        t0, n = time.time(), 0
        with open(dest, mode) as out:
            for chunk in r.iter_content(1 << 20):
                out.write(chunk)
                n += len(chunk)
                el = time.time() - t0
                if el < WINDOW:
                    continue
                rate = n / el
                t0, n = time.time(), 0
                if state['after'] is not None:  # the first window of a new connection
                    state['helpless'] = state['helpless'] + 1 if rate < state['after'] * 1.5 else 0
                    state['after'] = None
                state['best'] = max(state['best'], rate)
                if state['helpless'] >= HELPLESS:
                    continue
                if (state['best'] > 2 * SLOW_FLOOR and rate < state['best'] * SLOW_SHARE) or rate < SLOW_FLOOR:
                    out.flush()
                    raise Slow(rate, state['best'])
    finally:
        r.close()


def download(item, name, dest, size, md5):
    import internetarchive
    log = lambda s: print(s, flush=True)  # noqa: E731
    size = int(size)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    have = os.path.getsize(dest) if os.path.exists(dest) else 0
    if have > size:
        log('the local file (%d bytes) is larger than the archive one (%d): deleted' % (have, size))
        os.remove(dest)
        have = 0
    if have < size:
        log('downloading %s/%s (%s%s)' % (item, name, fmt(size),
                                         ', resuming from %s' % fmt(have) if have else ''))
        f = internetarchive.get_item(item).get_file(name)
        if f is None or not f.exists:
            sys.exit('the file %s does not exist in the item %s' % (name, item))
        state = {'best': 0.0, 'after': None, 'helpless': 0}
        attempt = 0
        while attempt < 5:
            attempt += 1
            t0 = time.time()
            before = os.path.getsize(dest) if os.path.exists(dest) else 0
            try:
                # The request is made here, from what is on disk (Range), with the item's
                # authentication (the S3 keys of ia.ini): the MD5 is checked below.
                fetch(f, dest, size, state)
            except Slow as e:
                # Not an error: a new connection, and the attempt is not counted.
                now = os.path.getsize(dest) if os.path.exists(dest) else 0
                log('the connection got slow at %s (%s): reconnecting' % (fmt(now), e))
                state['after'] = e.rate
                attempt -= 1
                time.sleep(1)
                continue
            except Exception as e:  # noqa: BLE001 - retoma onde parou
                now = os.path.getsize(dest) if os.path.exists(dest) else 0
                log('connection dropped at %s (%s): try %d of 5' % (fmt(now), e, attempt))
                if isinstance(e, PermissionError) or 'Forbidden' in str(e) or '403' in str(e) or '401' in str(e):
                    sys.exit('the Internet Archive refused the request (%s): check the S3 keys in '
                             '~/.config/internetarchive/ia.ini (ReXNative scripts/ia-keys.ps1)' % e)
                time.sleep(10 * attempt)
                continue
            now = os.path.getsize(dest) if os.path.exists(dest) else 0
            log('received %s in %.0f s' % (fmt(now - before), time.time() - t0))
            if now >= size:
                break
        have = os.path.getsize(dest) if os.path.exists(dest) else 0
        if have != size:
            sys.exit('the download stopped at %s of %s: try again to continue' % (
                fmt(have), fmt(size)))
    if md5:
        log('checking the MD5...')
        got = md5_of(dest, log)
        if got != md5.lower():
            bad = dest + '.md5-errado'
            os.replace(dest, bad)
            sys.exit('MD5 %s instead of %s: the file was renamed to %s (delete it and download again)'
                     % (got, md5, bad))
        log('MD5 correct (%s)' % got)
    log('done: %s' % dest)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == 'download':
        download(*sys.argv[2:7])
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
