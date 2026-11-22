#!/usr/bin/env bash
# Gestor ReXNative no Steam Deck: abre o Modo Deck em ecrã inteiro, num Firefox só dele (o perfil
# fica nesta pasta: o cookie que o identifica no PC, nada do Firefox de sempre). Quem faz o trabalho
# depende do modo: a app do PC, o próprio Deck (o modo Sem PC, em 127.0.0.1:8370) ou o PC quando
# responde e o Deck quando não (Automático).
# Instalado pela app do PC (Definições > Modo Deck) ou pelo modo Sem PC; o atalho do Steam corre isto.
here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
# gestor.conf: URLS (por onde se chega ao PC; vazio num Deck sem PC) e TOKEN (o deste Deck, para a
# app do PC; "local" num Deck sem PC)
URLS="" TOKEN=""
[ -f "$here/gestor.conf" ] && . "$here/gestor.conf"
URLS=$(echo $URLS)
LOCAL="http://127.0.0.1:8370"
# O modo (pc, local ou auto) vem do ficheiro mode, que o serviço do Deck e a app do PC escrevem (o
# gestor.conf não: o PC reescreve-o em cada atualização do lançador). Sem ele: o PC se há moradas
# do PC, senão o Deck.
mf="$HOME/.local/share/gestor-rexnative/mode"
mode=$([ -r "$mf" ] && tr -dc 'a-z' < "$mf")
case "$mode" in
  pc|local|auto) ;;
  *) if [ -n "$URLS" ]; then mode=pc; else mode=local; fi ;;
esac
# A lista por ordem (o start.html fica com a primeira que responde) e as outras moradas conhecidas,
# que o start.html oferece quando nenhuma da lista responde.
case "$mode" in
  local) list="$LOCAL"; rest="$URLS" ;;
  auto) list=$(echo $URLS $LOCAL); rest="" ;;
  *) list="$URLS"; rest="$LOCAL" ;;
esac
profile="$here/firefox"
mkdir -p "$profile"
cp -f "$here/user.js" "$profile/user.js"
rm -f "$profile/sessionstore.jsonlz4" "$profile/lock" "$profile/.parentlock"

# start.html procura o Gestor (as moradas e o token vão no fragmento #, que não sai do Deck) e abre
# /deck; sem ele mostra o que fazer. /run/udev (só leitura): o Firefox encontra os comandos pela
# base de dados do udev, que o flatpak não lhe mostra; sem ela o comando não mexe na página (o
# flatpak do Steam abre-a da mesma maneira).
u=$(echo $list | tr ' ' ',')
p=$(echo $URLS | tr ' ' ',')
flatpak run --filesystem="$here" --filesystem=/run/udev:ro org.mozilla.firefox --no-remote \
  --profile "$profile" --kiosk \
  "file://$here/start.html#t=$TOKEN&m=$mode&u=$u&p=$p"

# O Gestor fechou: quem fez o trabalho põe na biblioteca os jogos que chegaram entretanto (com o
# Steam fechado uma vez) e tira os atalhos dos que se apagaram. A primeira morada da lista que
# responde; depois as outras (o start.html pode ter aberto uma delas, sem resposta da lista).
for u in $list $rest; do
  curl -s -m 4 -X POST -H "X-Gestor: 1" -H "X-Gestor-Token: $TOKEN" "$u/api/remote/closed" \
    >/dev/null && break
done
exit 0
