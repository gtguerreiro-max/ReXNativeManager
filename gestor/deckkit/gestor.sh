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

# Os processos do Firefox do perfil.
ff_pids() { pgrep -f -- "^/app/lib/firefox/firefox .*--profile $profile( |\$)"; }
# As janelas do Firefox à vista (vazio sem o xdotool, que o SteamOS traz).
ff_windows() {
  command -v xdotool >/dev/null && xdotool search --onlyvisible --class firefox 2>/dev/null | wc -l
}

# Enquanto o Firefox recomeça, uma janela da app, escura, à frente (hp: o seu pid; o python3 e a
# libX11 vêm no SteamOS). Sem nenhuma, no segundo entre o Firefox antigo fechar e o novo abrir, o
# Steam punha o seu ecrã à frente da app e nem sempre a devolvia (o Deck ficava na página de um
# jogo da biblioteca, com o Gestor aberto atrás). Pedir-lhe a app (steam://rungameid) não serve:
# com ela a correr é um segundo arranque, que falha com um aviso "Game already running" que fica
# com o comando; um segundo perfil do Firefox, para o novo abrir antes de o antigo fechar, pedia
# outra vez que se aceitassem os termos do Firefox. Fecha-a o TERM, ou ela própria ao fim de 30 s.
hold_window() {
  hp=""
  command -v python3 >/dev/null || return
  python3 - <<'PY' &
import ctypes, signal, sys, time
try:
    x = ctypes.CDLL('libX11.so.6')
except OSError:
    sys.exit(0)
P, W = ctypes.c_void_p, ctypes.c_ulong
x.XOpenDisplay.restype, x.XOpenDisplay.argtypes = P, [ctypes.c_char_p]
x.XDefaultScreen.argtypes = [P]
x.XRootWindow.restype, x.XRootWindow.argtypes = W, [P, ctypes.c_int]
x.XDisplayWidth.argtypes = x.XDisplayHeight.argtypes = [P, ctypes.c_int]
x.XCreateSimpleWindow.restype = W
x.XCreateSimpleWindow.argtypes = [P, W, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                                  ctypes.c_uint, W, W]
x.XStoreName.argtypes = [P, W, ctypes.c_char_p]
x.XMapWindow.argtypes = x.XDestroyWindow.argtypes = [P, W]
x.XFlush.argtypes = x.XCloseDisplay.argtypes = [P]
d = x.XOpenDisplay(None)
if not d:
    sys.exit(0)
s = x.XDefaultScreen(d)
w = x.XCreateSimpleWindow(d, x.XRootWindow(d, s), 0, 0, x.XDisplayWidth(d, s),
                          x.XDisplayHeight(d, s), 0, 0, 0x0c0e10)  # the Deck page's background
x.XStoreName(d, w, b'ReXNative Manager')
x.XMapWindow(d, w)
x.XFlush(d)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
try:
    time.sleep(30)
finally:
    x.XDestroyWindow(d, w)
    x.XCloseDisplay(d)
PY
  hp=$!
}

# Abre o Gestor num Firefox (fp: o pid do flatpak); $1: "&tab=settings" depois de uma mudança de
# modo (o modo novo aparece em uso).
open_ff() {
  local tab=$1 mode u p
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
}

# Fecha o Firefox (o flatpak $1) como num "Sair" (TERM); preso, à força ao fim de 6 s.
close_ff() {
  local pid=$1 ff
  ff=$(ff_pids)
  [ -n "$ff" ] && kill -TERM $ff 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
  if kill -0 "$pid" 2>/dev/null; then
    ff=$(ff_pids)
    [ -n "$ff" ] && kill -KILL $ff 2>/dev/null
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
  fi
  wait "$pid" 2>/dev/null
}

open_ff ""
launches=1
while kill -0 "$fp" 2>/dev/null; do
  if [ -f "$rf" ] && [ "$launches" -lt 20 ]; then
    # Um segundo para a página dizer para onde vai; a janela escura; o Firefox fecha e abre outra
    # vez; quando a sua janela aparece (até 10 s; sem o xdotool, 3 s) a escura sai.
    sleep 1.5
    # "home" (the Automatic mode following the PC, rexdeck's _auto_watch): the page opens on its
    # first tab; a mode changed in Settings opens it there, the new mode in use.
    tab="&tab=settings"
    grep -q home "$rf" 2>/dev/null && tab=""
    rm -f "$rf"
    hold_window
    sleep 1
    close_ff "$fp"
    open_ff "$tab"
    launches=$((launches + 1))
    for i in $(seq 1 20); do
      kill -0 "$fp" 2>/dev/null || break
      w=$(ff_windows)
      if [ -n "$w" ]; then [ "$w" -gt 0 ] && break; else [ "$i" -ge 6 ] && break; fi
      sleep 0.5
    done
    sleep 0.5
    if [ -n "$hp" ]; then kill -TERM "$hp" 2>/dev/null; wait "$hp" 2>/dev/null; fi
    continue
  fi
  sleep 1
done
wait "$fp" 2>/dev/null
rm -f "$rf"

# O Gestor fechou: quem fez o trabalho põe na biblioteca os jogos que chegaram entretanto (com o
# Steam fechado uma vez) e tira os atalhos dos que se apagaram. A primeira morada da lista que
# responde; depois as outras (o start.html pode ter aberto uma delas, sem resposta da lista).
for u in $list $rest; do
  curl -s -m 4 -X POST -H "X-Gestor: 1" -H "X-Gestor-Token: $TOKEN" "$u/api/remote/closed" \
    >/dev/null && break
done
exit 0
