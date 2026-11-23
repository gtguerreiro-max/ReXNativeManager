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
# A mudança de modo nas Definições pede um recomeço: quem gravou o modo (o serviço do Deck, ou a
# app do PC por SSH) escreve também o ficheiro relaunch, e este script fecha o Firefox e abre-o
# outra vez já no lado do modo novo (o start.html escolhe). A página deixou de passar de um Gestor
# para o outro (location.replace do PC para 127.0.0.1:8370 ou ao contrário): o Firefox 154 do Deck
# ficava às vezes preso nessa passagem (o processo principal a 100%, a página sem se desenhar), e
# a app parecia ter ido abaixo.
rf="$here/relaunch"
profile="$here/firefox"
mkdir -p "$profile"
rm -f "$rf"
launches=0
while :; do
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
  cp -f "$here/user.js" "$profile/user.js"
  rm -f "$profile/sessionstore.jsonlz4" "$profile/lock" "$profile/.parentlock"
  # Depois de uma mudança de modo, as Definições outra vez (o modo novo aparece em uso).
  tab=""
  [ -f "$rf" ] && tab="&tab=settings"
  rm -f "$rf"

  # start.html procura o Gestor (as moradas e o token vão no fragmento #, que não sai do Deck) e abre
  # /deck; sem ele mostra o que fazer. /run/udev (só leitura): o Firefox encontra os comandos pela
  # base de dados do udev, que o flatpak não lhe mostra; sem ela o comando não mexe na página (o
  # flatpak do Steam abre-a da mesma maneira).
  u=$(echo $list | tr ' ' ',')
  p=$(echo $URLS | tr ' ' ',')
  flatpak run --filesystem="$here" --filesystem=/run/udev:ro org.mozilla.firefox --no-remote \
    --profile "$profile" --kiosk \
    "file://$here/start.html#t=$TOKEN&m=$mode&u=$u&p=$p$tab" &
  fp=$!
  again=""
  while kill -0 "$fp" 2>/dev/null; do
    if [ -f "$rf" ]; then
      # Um segundo para a página dizer para onde vai; depois o Firefox fecha como num "Sair" (TERM)
      # e, se estiver preso, à força ao fim de 6 s.
      again=1
      sleep 1.5
      ff=$(pgrep -f -- "^/app/lib/firefox/firefox .*--profile $profile( |\$)")
      [ -n "$ff" ] && kill -TERM $ff 2>/dev/null
      for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do kill -0 "$fp" 2>/dev/null || break; sleep 0.5; done
      if kill -0 "$fp" 2>/dev/null; then
        ff=$(pgrep -f -- "^/app/lib/firefox/firefox .*--profile $profile( |\$)")
        [ -n "$ff" ] && kill -KILL $ff 2>/dev/null
        sleep 1
        kill -0 "$fp" 2>/dev/null && kill -KILL "$fp" 2>/dev/null
      fi
      break
    fi
    sleep 1
  done
  wait "$fp" 2>/dev/null
  [ -f "$rf" ] && again=1  # gravado enquanto o Firefox fechava
  launches=$((launches + 1))
  [ -n "$again" ] && [ "$launches" -lt 20 ] && continue
  break
done
rm -f "$rf"

# O Gestor fechou: quem fez o trabalho põe na biblioteca os jogos que chegaram entretanto (com o
# Steam fechado uma vez) e tira os atalhos dos que se apagaram. A primeira morada da lista que
# responde; depois as outras (o start.html pode ter aberto uma delas, sem resposta da lista).
for u in $list $rest; do
  curl -s -m 4 -X POST -H "X-Gestor: 1" -H "X-Gestor-Token: $TOKEN" "$u/api/remote/closed" \
    >/dev/null && break
done
exit 0
