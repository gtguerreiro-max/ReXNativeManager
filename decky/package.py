"""Empacota o plugin Decky (depois de `npm run build`) em gestor/static/deck-plugin.zip: a pasta
gestor-rexnative/ com plugin.json, package.json, main.py e dist/index.js, como o Decky a quer
("Instalar plugin a partir de um ZIP" ou de um endereço, nas definições de programador)."""
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'gestor', 'static', 'deck-plugin.zip')
FILES = ['plugin.json', 'package.json', 'main.py', 'dist/index.js']


def main():
    # O main.py tem de estar inteiro: um nome em falta (como o _conf que a 1.4.3 perdeu) só se via no
    # Deck, com o plugin "sem ligação ao PC".
    import subprocess
    import sys
    r = subprocess.run([sys.executable, '-m', 'pyflakes', os.path.join(HERE, 'main.py')],
                       capture_output=True, text=True)
    if 'undefined name' in r.stdout or r.returncode not in (0, 1):
        raise SystemExit('main.py has errors:\n' + r.stdout + r.stderr)
    for f in FILES:
        if not os.path.exists(os.path.join(HERE, f)):
            raise SystemExit('falta %s: corre npm install && npm run build primeiro' % f)
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            data = open(os.path.join(HERE, f), 'rb').read().replace(b'\r\n', b'\n')
            info = zipfile.ZipInfo('gestor-rexnative/' + f, date_time=(2026, 11, 19, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    print(OUT, os.path.getsize(OUT))


if __name__ == '__main__':
    main()
