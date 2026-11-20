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
        for attempt in range(1, 6):
            t0 = time.time()
            before = os.path.getsize(dest) if os.path.exists(dest) else 0
            try:
                # Sem checksum: só assim a biblioteca retoma o ficheiro parcial (o MD5 é
                # verificado abaixo). Os erros sobem (ignore_errors=False).
                # destdir + só o nome: um caminho absoluto em file_path seria tornado relativo
                # (C: -> C%3A) pela biblioteca no Windows.
                f.download(file_path=os.path.basename(dest), destdir=os.path.dirname(dest),
                           retries=5, timeout=120, ignore_errors=False)
            except Exception as e:  # noqa: BLE001 - retoma onde parou
                now = os.path.getsize(dest) if os.path.exists(dest) else 0
                log('connection dropped at %s (%s): try %d of 5' % (fmt(now), e, attempt))
                if 'Forbidden' in str(e) or '403' in str(e) or '401' in str(e):
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
