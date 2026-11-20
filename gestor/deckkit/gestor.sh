#!/usr/bin/env bash
# Gestor ReXNative no Steam Deck: abre o Modo Deck da app do PC em ecrã inteiro, num Firefox só
# dele (o perfil fica nesta pasta: o cookie que o identifica no PC, nada do Firefox de sempre).
# Instalado pela app do PC (Definições > Modo Deck); o atalho do Steam corre este script.
here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
# gestor.conf: URLS (por onde se chega ao PC) e TOKEN (o deste Deck, para a app do PC)
. "$here/gestor.conf"
profile="$here/firefox"
mkdir -p "$profile"
cp -f "$here/user.js" "$profile/user.js"
rm -f "$profile/sessionstore.jsonlz4" "$profile/lock" "$profile/.parentlock"

# start.html procura o PC (as moradas e o token vão no fragmento #, que não sai do Deck) e abre
# /deck; sem PC mostra o que fazer. /run/udev (só leitura): o Firefox encontra os comandos pela
# base de dados do udev, que o flatpak não lhe mostra; sem ela o comando não mexe na página (o
# flatpak do Steam abre-a da mesma maneira).
urls=$(echo $URLS | tr ' ' ',')
flatpak run --filesystem="$here" --filesystem=/run/udev:ro org.mozilla.firefox --no-remote \
  --profile "$profile" --kiosk \
  "file://$here/start.html#t=$TOKEN&u=$urls"

# O Gestor fechou: a app do PC põe na biblioteca os jogos que chegaram entretanto (com o Steam
# fechado uma vez) e tira os atalhos dos que se apagaram.
for u in $URLS; do
  curl -s -m 4 -X POST -H "X-Gestor: 1" -H "X-Gestor-Token: $TOKEN" "$u/api/remote/closed" \
    >/dev/null && break
done
exit 0
