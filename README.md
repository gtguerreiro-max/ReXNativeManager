<div align="center">

# ReXNative Manager

**Your Xbox 360 games, recompiled with ReXGlue and drawn by ReXNative, from the archive to the
Steam Deck: download, build, test, fix with an AI assistant, and play from the couch.**

![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)
![Steam Deck](https://img.shields.io/badge/Steam%20Deck-Deck%20mode%20%7C%20Decky-1A9FFF?logo=steamdeck&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![AI](https://img.shields.io/badge/AI-Claude%20Code%20%7C%20Codex%20%7C%20Gemini%20%7C%20Ollama-D97757?logo=anthropic&logoColor=white)
[![ReXNative](https://img.shields.io/badge/renderer-ReXNative-5FBF3F)](https://github.com/gtguerreiro-max/ReXNative)
![License](https://img.shields.io/badge/license-MIT-blue)
![Game files](https://img.shields.io/badge/game%20files-not%20included-lightgrey)

</div>

[ReXGlue](https://github.com/rexglue/rexglue-sdk) recompiles an Xbox 360 game's PowerPC code to x64,
and [ReXNative](https://github.com/gtguerreiro-max/ReXNative) draws it natively with Direct3D 12.
Getting one game from an archive to a working build takes a dozen steps: extract, title update,
DLC, code generation, the renderer's layer, the project, the build, a test that it draws. **The
Manager does all of it for every game**, tests each build against the classic renderer, has an AI
assistant fix what fails, and installs the result on a Steam Deck, which you then drive from the
couch with the controller.

> [!IMPORTANT]
> No games, game sources or game data are in this repository, and the app ships with none: you add
> the sources you want, and you need your own copy of each game.

## Features

- **Your own games, as you have them:** a dump in a folder (with `default.xex`), a disc image
  (`.iso`), an archive (`.7z`, `.zip`, `.rar`) or an Xbox Live package. **Add your own game…**
  takes one; your game folders put all of theirs in the catalogue, ready to install from the Deck.
- **A catalogue:** your game folders and the sources you add, with covers, genre, year and
  Metacritic score; search, filters, and downloads with resume and MD5 checks.
- **Build and test on the PC:** prepare, build and boot each game; captures of the native
  renderer and the classic one at the same moment, compared by a model that sees images; a second
  test with the Steam Deck's settings; the classic renderer instead of an error when the native one
  cannot draw a game yet.
- **An AI assistant that fixes what fails:** Claude Code, OpenAI Codex, Gemini CLI, Antigravity, or
  a local model (Ollama, LM Studio). It reads the failure, fixes ReXNative or the game's folder,
  and the step runs again; **Report a problem** sends it to investigate with the game running.
  Fixes from anyone who cannot push to ReXNative go back to it as pull requests.
- **Up to date or not:** every build records the ReXNative commit and SDK it was made with; each
  game says which fixes it lacks, and **Rebuild outdated** brings them all up.
- **Play:** on this PC (the game page, or the Play button on each card) or on the Deck through its
  Steam, from the PC or from Deck mode. On the PC, a controller or the keyboard (Enter Start, Space A,
  W A S D move, arrows look); the Manager says when no controller is connected.
- **Steam Deck:** install (internal storage or microSD), update, delete with a backup of the saves,
  per-game settings, the Steam artwork, the library shortcuts.
- **Deck mode:** the Manager on the Deck itself, fullscreen in Game Mode for the controller: your
  Deck games with each one's versions and fixes, the games on the PC, the catalogue (pick a game
  and it arrives in your library), requests, free space, **Play**, and reports from the Deck.
- **Snapshots for reports:** in the game, the settings menu and Y save that moment (the picture
  and the next frames as a trace); the next report sends them, and Claude replays those frames.
- **Achievements:** each game's Xbox 360 achievements (name, description, gamerscore, icon; secret
  ones stay hidden until unlocked), with the ones you unlocked on the Deck or the PC and when, on the
  game page and in Deck mode, which also tells you about new ones.
- **Decky plugin:** what the PC is doing and the games played last, in the quick access menu.
- **ReXNative changelog:** every change by day, the games it names, and whether your PC and Deck
  builds have it yet.
- **Linux builds** (experimental): a native Linux build per game, sent beside the Windows one.
- **Versions:** what changed in each version, and the app updates itself from GitHub when idle.

## Quick start

You need Windows 10 or 11, Python 3.11+, the GitHub CLI, an AI assistant on the command line, and
what ReXNative needs to build ([details](#getting-started)).

```powershell
git clone https://github.com/gtguerreiro-max/ReXNativeManager
cd ReXNativeManager
.\iniciar.bat
```

The page opens at `http://127.0.0.1:8360/`: sign in with GitHub, pick the assistant, add your
catalogue sources, and, for a Steam Deck, its SSH address. Settings > Deck mode then installs the
Manager on the Deck.

## How it works

From download to the Steam Deck:

1. **Catalogue**: your own games (below) and the games in the sources you add, and a search for
   the ones not there.
   **Your own games** (`gestor/owngames.py`): **Add your own game…** (My games, Catalogue) takes a
   dump folder (with `default.xex`), a disc image (`.iso`), an archive (`.7z`, `.zip`, `.rar`) or an
   Xbox Live package (STFS), typed in or chosen in a Windows window, says what it found, and
   prepares, builds and tests it. Settings > "Your game folders" (or "Add it to your game folders"
   there) lists folders the app looks through, four levels down: their games appear in the catalogue
   as the source **Your files**, in the PC app and in Deck mode, where **Install on the Deck** goes
   straight to preparing from your file (no download; a game of yours wins over a source's copy of
   the same game). Prepared games' folders and the downloads folder are left out.
2. **Downloads**: only what you choose, with resume and MD5 verification.
3. **Prepare, build and test**: `python -m rexnative prepare ... --title-update --dlc --project`
   (title update from XboxUnity, DLC when available), then a boot test on the PC with
   `scripts\live.ps1` (the game has to draw frames without crashing).
   The boot test takes renderer captures at 15, 30, 45 and 60 s (the app asks the renderer itself:
   `<run>\live\cap\capture.request`, no PowerShell per capture) and, right after each one, flips the
   renderer switch (`renderer stock` in `live\control.txt`, the game's F9) to take the same moment
   from the classic renderer (ReXGlue's, Xenia's) 1.5 s later, then flips it back
   (`compare_one_run`, `compare_switch_wait`). Only when those classic captures are not usable does
   a second run start with `--rexnative_classic=true`. The cheap model looks at the pairs side by
   side and says whether the native one has graphical errors (the game is marked "native with
   errors" and the pairs go with the report). The game log is read incrementally (only what it grew).
   **With the Deck settings** (step "Test with the Deck settings", `deck_test_enabled`):
   the game starts again on the PC with what the Deck will use (`rexnative.deck.package`: the
   kit's Deck settings with the game's on top, passed as `--section.name=value`; 1280x800, the
   upscaler in Native AA with FSR, not fullscreen), captures at the same seconds, and the cheap
   model compares them with the boot test's (and how much more of the image is black). With
   errors the game is marked "Deck: errors" and an automatic report goes to Claude, as a Deck
   problem. Tetris Splash only showed its left half with the upscaler: this made it visible on the PC.
   Deck mode requests and the "Rebuild" of Deck games go through this test.
   **Classic renderer instead of an error**: when the native renderer does not get through the boot
   test and Claude finds no fix, the same boot test runs on ReXGlue's classic renderer (Xenia's);
   if the game runs there it starts on it from then on (`[rexnative] classic = true` in
   `run/<name>.toml` and `deck.toml`; the HUD still switches to the native one), the game is marked
   "classic (native failed)" and the pipeline goes on (`classic_fallback` in the settings).
   **Up to date or not**: each build records what it was built with (`run/rexnative-build.json`,
   from ReXNative 4b6940d on: the commit, whether there were local changes, the SDK's identity).
   The app compares that with the published `main` and with the SDK installed now: each game says
   "up to date", "N missing" (the ReXNative fixes that go into the game, `renderer/` and the
   generator in `rexnative/`, with the list) or "new SDK". An older build is compared by date.
   "Rebuild outdated" (all, or only the ones on the Deck) builds and tests each one and resends
   to the Deck the ones that are there; Deck mode shows "New fixes" and has "Rebuild and send".
4. **Automatic fixing with Claude Code**: when a step fails, the app runs `claude -p` with the
   failure log; Claude fixes ReXNative (commit and push following the repository rules) or the
   game folder, and the app repeats the step, up to a limit of attempts. The job shows what
   Claude read, changed and published.
   A Claude session is stopped after `claude_timeout_min` (120 min by default: the build queue
   waits for it), and the game it left running with `live.ps1` is closed so the next boot tests
   are not blocked. Changes a failed or cancelled session left uncommitted in the app's ReXNative
   worktree are put aside in `git stash` ("gestor: left over before <job>") before the next job,
   so they are not built into other games. Testing the suspect games of a fix, and the rebuild
   after a report, never fall back to the classic renderer: a game that only runs on the classic
   one there counts as worse (the fallback would hide what the change broke).
   **Report a problem** on each game: the type (graphics in native, crashes, slow, sound...), where
   (PC, Deck), what you see and the captures that show it; Claude (the strong model) investigates
   with the game running, fixes, builds, and the game is tested again. Until there is a fix, a
   button puts the game on the classic renderer (PC or Deck).
   **Snapshots**: at the place, in the game, the settings menu (View + Menu on the Deck, Back +
   Start or F1 on the PC) and then Y saves that moment in the game's `snapshots\` folder: the frame
   as shown and a frame trace of the next frames (ReXNative's renderer). A report sends the newest
   ones (the last day's): from the Deck they come with the report ("Send the snapshots you took",
   on by default, and the automatic screenshot is then off), on the PC Claude finds them in
   `run\snapshots`. Claude looks at the picture and plays the trace on the PC first: what the game
   handed the renderer there, with no place to reach (the Deck runs the same executable); right on
   the PC while the Deck's picture is wrong, the fault is in what differs on the Deck. Deck mode
   counts them on the game's sheet and says when a new one was taken.
   The instructions it gets (`claude.REPORT_PROMPT`) are about spending its time well, measured on
   the reports so far (where an hour went: reaching the place again after every rebuild, waiting
   minutes blind, searching the recompiled game's code). It reaches the place once (with the
   player's save, pad routes), records a frame trace there at once (`live.ps1 record`), and after
   each rebuild plays that trace (`live.ps1 play`, about 20 s) instead of reaching the place
   again; the trace is also kept as the game's test scene. It sorts the fault with ReXNative's
   tools before reading code (the Xenos renderer at the same spot, `-Oracle`, `compare`, `audit`,
   `idle`, RenderDoc `summary`; the log for sound, crashes and speed), searches the renderer's
   sources and docs, not the generated code (`watch` names what writes an address), and
   rebuilds once per idea. It also gets the game's test scenes, to play at once. When the player
   left a snapshot, the report opens with it (its picture, what the player saw, and its trace) and
   Claude starts there: it plays the trace on the PC and sets it beside the picture (wrong the same
   way: the trace is its fast loop and the place's test scene; right on the PC: it plays it with the
   Deck's settings, or the fault is the Deck's own), and reaches the place live only for what a
   trace does not hold. When it cannot reach the place and has no snapshot, it asks for one. The assistant's
   sessions have a `live.ps1` state folder of their own (`REXNATIVE_LIVE_STATE`,
   `%LOCALAPPDATA%\rexnative-live-manager`): another session's live game is never in their way,
   and the app closes the game a session left running in either folder.
5. **Steam Deck**: install (`python -m rexnative deck --steam --try 35`, on internal storage or the
   microSD card), see what is installed and the free space, delete a game (with confirmation and a
   backup of the saves; the Steam shortcut goes too).
   A deleted game is marked on the Deck (`~/Games/ReXNative/.removed/<game>`): a `rexnative deck`
   from another program that resends a list of games leaves it out (installing through the app
   removes the mark). Deck jobs wait while another program on the PC is sending to it (`python -m
   rexnative deck`, `deck_drive.py`), which the page also shows. Sending has a progress bar, with
   MB/s and the time left (from the `copied N of M MB` lines of `rexnative deck`; downloads also
   show the speed and the time left). Before sending it checks there is space; if the connection
   drops midway (the Deck's Wi-Fi switches band), it resumes up to 3 times from where it was, and
   a send that stopped midway shows as "incomplete send", with **Complete**, just like a game
   without a Steam shortcut.
   The Deck list has checkboxes to pick several games and delete them at once: a backup of each,
   all the shortcuts with Steam closed just once, and the folders. Along with the shortcut go that
   shortcut's artwork, shader cache and Steam prefix (otherwise they stayed behind: on 2026-11-19
   there was 1.2 GB of caches for games that no longer existed).
6. **Per-game settings**: `deck.toml` (what the Deck uses on top of the kit's settings) and
   `run/<name>.toml` (the PC), with a form for the common options and the file by hand; then
   resend to the Deck.
7. **Covers**: the official ones (box scans from XboxUnity, images from the Xbox 360 Marketplace;
   SteamGridDB if you give it a key), composed in `<work>/deck/art` (portrait 600x900, grid
   920x430, hero 1920x620, icon), which the Deck kit hands to Steam. You choose in the app, or the
   cheap model (Haiku) chooses by looking at them ("Choose automatically"; a new game gets them at
   the end of the pipeline).

The catalogue and your games show the genre, the year, the developer and the Metacritic score
(sort by score, filter by genre): from Wikidata (free data, all Xbox 360 games at once) and from
the English Wikipedia review tables (`MC_X360`), cached and re-read every 14 days. About 90% of
the games have a genre and 60% have a score.

Game fixes use the most capable model (Opus, high effort); the cheap model only picks covers and
runs the self-test. With a Claude subscription session nothing is charged separately: the cost the
app shows is Claude Code's estimate at API prices.

The interface is a local page in English, at `http://127.0.0.1:8360/`.

## Deck mode: the Manager on the Steam Deck

A shortcut in the Deck's Steam library, **Gestor ReXNative**, opens the app fullscreen in Game
Mode (`/deck`), made for the 1280x800 screen and the controller: the D-pad and the stick move, A
selects, B goes back, X searches, Y sorts, L1/R1 switch tabs, Menu exits. Touch works too.
L2/R2 jump in the game grids: to the previous or the next letter in a list sorted by name (the
letter shows in the middle of the screen; hold for letter after letter), three rows at a time in
any other order. The app opens on the tab it was left on, and on every tab but Requests a strip
under the top bar shows the request the PC is working on, its stage and its progress.

- **On the Deck**: the installed games with their covers, the free space, "Update" when the PC
  has a newer build; on each game, update, the quick settings (renderer, upscaler, FPS limit) and
  delete (with a copy of the saves to the PC).
- **Play** on a Deck game: the Manager closes and the PC starts the game through Steam once it has
  closed (the Decky plugin also lists the games played last, each one a Play button).
- **Search and sort** in On Deck (name, last played, size, recently sent) and On PC (name, recently
  built, Metacritic). **Free space** lists the Deck games from the biggest, with when each was last
  played, to delete several at once (the saves are copied to the PC first); it lights up when the
  Deck runs low.
- **What ReXNative tunes for this game** on the card (`gestor/tunings.py`): read from the game's
  generated layer (`layer/layer.json`: the XDK's Direct3D, draws from the push buffer, command
  buffers, occlusion, devices, remapped arguments, the scene, hand overrides) and its `[rexnative]`
  settings for the PC and the Deck.
- **On PC**: the games prepared on the PC, with their covers and badges (on the Deck, not built,
  new fixes, classic renderer, errors seen by the tests) and filters; each one's sheet says when it
  was built, which ReXNative fixes it lacks and how the tests went (boot, native vs classic, Deck
  settings), and offers Install on the Deck (internal storage or microSD), Build or Rebuild.
- **Catalogue**: the games from your folders and your sources with the official covers (XboxUnity looks them
  up by name, without downloading anything; they are cached), Metacritic, genre, search with the
  on-screen keyboard, filters. **Install on Deck** places a request: the PC downloads, prepares,
  builds and tests (with Claude's fixes if it fails) and sends it to the Deck; whatever is already
  done is skipped.
- **Changelog**: every ReXNative change on main, by day (`gestor/rexlog.py`, `static/rexlog.js`):
  its area (from the subject and the files it touches), the games it names (this PC's and those in
  ReXNative's `docs/GAMES.md`, by name: "Overlord" alone is not Overlord II) with a dot for whether
  your build has it (green: on the Deck or in the PC build; blue: built on the PC, update the Deck;
  yellow: not built in yet). A opens the whole change; X searches; Y changes what is shown; pick a
  game to see what mentions it or what its Deck or PC build lacks. New changes since the last look
  are marked; branches with work not in main yet open on their own sheet.
- **Each game's card** (A on a Deck game): the version on the Deck (when it was built, with which
  ReXNative version, when it arrived), the PC's if it is newer and what it brings, the fixes not
  yet built, the history of sends with what each one fixed, and the game's reports with what
  Claude found (Claude's summaries are in English). Fixes are listed by their commit subject,
  shown as it is (`changelog.py`; no translation); each send to the Deck is recorded
  (`deck_versions`).
- **Report a problem** (on each Deck game): what you see (quick picks, like "only part of the
  screen shows", and text via the on-screen keyboard); the app gathers what the Deck knows about
  the game (the latest log, the settings it uses there, the Steam screenshots from the last 24 h,
  Steam + R1) and, if requested, a capture on the Deck (the game opens through Steam with the
  renderer capture request, is captured at N seconds and closes). **Send my save** (on by default)
  copies the game's saves from the Deck into the PC copy, so Claude plays from your progress and
  reaches a menu or level a new game does not have (the PC's own saves are kept in
  `backups/pc`; the Deck's save is not changed). Claude investigates on the PC
  knowing it is a Deck problem (reproducing with the Deck settings); if it fixes it, the game is
  built, tested and resent to the Deck. The report shows up in Requests (Collect on Deck, Claude
  investigates, Send the fix) with what Claude found.
- **The assistant's conversation**: open a request in Requests to follow what the assistant says
  and does (Claude or the one chosen in Settings), live; while Claude works, **X** writes to it
  with the on-screen keyboard (a hint, what you saw, where to look) and the message reaches it in
  what it is doing. On the PC, the job view has the same box.
- **Requests**: the stages of each one (Download, Build on PC, Send to Deck, Library) with the
  progress, the speed and the time left; cancel and retry. Under the title, what the PC is doing
  now (the jobs running in the build lane and in the report lane, for how long, and how many
  wait), so a request that waits says what for.
  Inside "Build on PC", the phases of the current step (`progress.py` reads the step's log):
  extracting, the game update and the DLC downloading (with %), each round of code generation,
  the game runs to find functions (N of 12), the build (file N of M, from ninja), the boot test
  (seconds), Claude fixing (the last tool it used), and the time in the step and since the
  request. The PC app's jobs show the same.
  What you start from the Deck besides installing and reporting (Rebuild, Update or Complete,
  Save and send, Delete, Restore saves, Update the launcher) also shows up here, labelled, with its
  progress, and can be opened; an open request keeps updating.
- **Install to** the internal storage or the microSD card (when the Deck has one), with the free
  space of each. **Restore saves** on a Deck game puts back one of the copies the PC keeps from
  deleting it.
  A request made from the Deck that is then put to sleep waits for it to wake up to send the
  game (up to `deck_wait_hours`, 12 by default) instead of failing.

The page asks the PC with a 10 s limit (a PC asleep shows "No connection" instead of a page that
hangs), only redraws what changed (progress updates in place, covers already loaded do not fade in
again), and asks for the catalogue with the signature of the one it has (the PC sends it only when
it changed). A `/deck` page opened on the PC itself does not count as the Manager open on the Deck.

The PC does all the work: building needs Windows, the ReXGlue tools and the PC's graphics card,
and the archives are terabytes; the Deck only chooses and receives. The PC has to be on, with the
app open ("Start the Manager with Windows" in Settings helps; Wake-on-LAN does not work over the
PC's Wi-Fi).

With the Manager open on the Deck, Steam cannot close (that would close the Manager): games reach
the Deck right away, but the shortcut enters the library when you exit the Manager (Steam restarts
for a few seconds, once for all of them); the same goes for the shortcuts of deleted games. If
Steam closes the Manager without going through "Exit", the app notices the page stopped sending a
heartbeat and does the same.

**Install**: Settings > Deck mode > Install the Manager on the Deck. The app then also answers on
the home network (one server per private address of the PC, besides the one on 127.0.0.1),
creates the Deck's token and writes it there over SSH (nothing to type on the Deck), sends the
launcher (`gestor/deckkit/`: `gestor.sh`, the start page that looks for the PC by address and by
the name `<pc>.local`, the Firefox preferences) to `~/.local/share/gestor-rexnative` and adds the
shortcut with its own artwork. It uses the Firefox the Deck already has (flatpak), with a profile
of its own.

**Security**: from outside this PC only Deck mode can be reached (`/deck`, `/api/remote/...`), with
the option on, from a private address, with this PC's Host (against DNS rebinding) and with the
token of a paired device (HttpOnly cookie; the app stores only the SHA-256). The rest of the API
stays on 127.0.0.1 only. Another device (a phone) pairs with a 6-digit code the app shows for 5
minutes; devices are revoked in Settings.

**Decky plugin** (`decky/`): in the quick access menu (…) it shows the requests with their
progress, notifies you when a game is ready (even while playing something else), opens the Manager
and adds to the library what is waiting. It uses the Manager's token on the Deck.
**Install or update it** with "Install the Decky plugin on the Deck" (PC app, Settings > Deck mode),
"Install / Update the Decky plugin" (Deck mode, What's new) or, once installed, "Update the
plugin" in its own panel when the PC has a newer one: the ZIP goes to
`~/Downloads/gestor-rexnative-decky-<version>.zip` on the Deck and Decky installs it and reloads
it (Decky's local API, `utilities/install_plugin`, the same as "Install Plugin from ZIP File").
Decky keeps only one connection to that API: the request takes the Deck interface's place for a
few seconds (it reconnects by itself), so Decky's "install?" window comes to the request, which
confirms it (`utilities/confirm_plugin_install`): the button you pressed, after its own
confirmation, is the choice. By hand: Decky > Developer > Install Plugin from ZIP File with that
file, or from the URL `http://<pc>:8360/static/deck-plugin.zip`. Build: `cd decky && npm install &&
npm run build && python package.py` (raise the version in `decky/package.json` first).

## Linux builds (experimental)

ReXNative draws with D3D12, so a game is a Windows executable that runs on the Deck under Proton.
ReXGlue also builds for Linux, drawn by its own renderer on Vulkan (the Xenos GPU emulation).
Measured on the Deck (`docs/LINUX.md` in ReXNative), a native Linux build runs, with about 8 % less
CPU than under Proton, but that renderer uses far more GPU than ReXNative: the Windows build stays
the default and a Linux build is made only when asked, per game (`gestor/linuxbuild.py`):

- **Build for Linux** (the game's page on the PC, or its sheet in Deck mode): the app keeps a copy
  of ReXNative on the branch with the Linux tools (`linux_branch`), writes the project files with
  its `REXNATIVE` option and runs `scripts/linux/build-game.sh` in WSL with the ReXGlue SDK built for
  Linux (`linux_sdk`, a path inside WSL), in a copy at `linux_builds_dir/<game>`.
- **Send to the Deck and use it**: the build goes to `<game folder>/linux/` beside the Windows
  build (its `game/` is a link to the Windows build's) and two lines in the game's `deck.env`
  (`REXNATIVE_PROTON` = the proton shim, `REXNATIVE_LINUX_BUILD` = `linux/`) make `play.sh` start
  it. **Start the Windows build** removes them. Saves are separate.

Settings > "Linux builds" turns it on (off by default) and takes the WSL distribution and the SDK.

## PC pages

- **Compatibility**: every game with its build, the ReXNative fixes it lacks, the boot test (FPS),
  native vs classic, the Deck settings test, the renderer on the PC and the Deck, the XDK and the
  Metacritic score; sortable by any column, filterable, exportable as CSV.
- **Storage**: the free space of each drive; each game folder by parts (the extracted game, the
  archive copy kept in the folder, the build, the run folder; "Measure the game folders" walks them
  in the background); the downloaded archives, with "Delete the archives already prepared".
- **ReXGlue SDK** (Settings, `gestor/sdk.py`): the installed version, our changes on top of the
  official SDK (the fork), the official commits not in it yet, the latest release and nightly on
  GitHub with their notes, and "Update and rebuild the SDK": `git fetch`, the current state kept
  in a `backup/sdk-<date>` branch, our changes rebased on the official `main` (a conflict undoes it
  and changes nothing), then `build-llvm20.cmd` in the build lane, waiting for other sessions' builds.

- **Changelog**: the same ReXNative changelog as in Deck mode, with a side panel of your games and
  how many changes each one's Deck build (or PC build) is behind; click a game to list them. Each
  change opens in place with its description, its files and a link to the commit on GitHub; "Check
  GitHub now" fetches at once (otherwise every 5 minutes).

## Versions

The app has a version (`gestor/version.py`: `VERSION` and `CHANGES`, what each version changes,
newest first); each change to what the app does raises it (x.y.z: y for new features, z for
fixes) and the commit gets the git tag `vX.Y.Z`. The PC page shows the running version at the
top; it turns yellow when a newer one is on disk (a commit not restarted yet) or on GitHub
(`origin/main`, checked every 30 minutes). Clicking it shows what changed and offers **Update from
GitHub and restart** (`git pull --ff-only`, refused with uncommitted changes) or **Restart**: the
app restarts by itself once the jobs that are running end (`POST /api/version/update`,
`/api/version/restart`; a hidden PowerShell waits for it to exit and opens `iniciar.bat` again).
The queue survives it: queued jobs do not start while a restart is pending and are back in the
queue, in order, when the app opens again; requests from the Deck, a download and a transfer that
waits for a sleeping Deck give their turn back and pick up where they were. The same happens when
the app is closed with jobs queued (the job that was running is marked interrupted).

Jobs run in lanes: downloads in parallel (`max_downloads`), builds and tests one at a time (the
build lane), reports one at a time in a lane of their own, Deck transfers one at a time. A report
is investigated beside whatever the build lane does, in a second copy of ReXNative that only
reports use (`report_rexnative_dir`, by default the app's copy with `-reports`, a git worktree made
the first time) and with its own live game. Only one job at a time builds or tests a given game,
the test bench runs one game at a time, and an SDK update keeps the report lane closed.
`report_lane` off puts reports back in the build lane. `python scripts/test_jobs.py` tests the
queue with made-up jobs.
Deck mode shows the version in its status line, opens "What's new" once after the PC updated, and
has "What's new" in the Exit menu.

What the app writes to its console (errors, tracebacks of its threads, uvicorn's warnings) also
goes to `data_dir/logs/server.log`, each line with its time; after a restart the app runs hidden,
so this is where an error is seen. It starts over (the old one becomes `server.log.1`) when it
passes 2 MB at a start. The version window links to it (**Server log**, `GET /api/server/log`).

The Deck launcher (`gestor/deckkit/`, `deckapp.VERSION`) and the Decky plugin
(`decky/package.json`) have their own versions: the app knows the launcher it installed and the
plugin version the plugin reports when it asks (`/api/remote/home?plugin=`). A newer launcher shows
in Deck mode with **Update** (only the files: Steam does not restart); a newer plugin is
installed in Decky from `http://<pc>:8360/static/deck-plugin.zip`.

## Getting started

```
iniciar.bat
```

The first time, it creates a Python environment in `.venv` (with access to the system Python's
packages, where ReXNative already has what it needs) and installs FastAPI and uvicorn; then it
opens the page in the browser. `iniciar.bat --no-browser` does not open the browser; `--port N`
changes the port.

It needs:

- Python 3.11 or newer on the PATH;
- the GitHub CLI (`winget install GitHub.cli`) and a GitHub account: signing in is required
  (below);
- an AI assistant on the command line with a signed-in session: Claude Code, OpenAI Codex (with a
  ChatGPT account), Gemini CLI or Antigravity CLI (below);
- what ReXNative needs to build (the ReXGlue SDK, LLVM, FidelityFX: the paths go in Settings, under
  "Environment variables"); the app clones ReXNative itself into `~\ReXNativeManager\ReXNative`
  the first time;
- your games: your own files (**Add your own game…**, or Settings > "Your game folders"), and, if
  you want, Settings > "Catalogue sources" for Internet Archive items to list (the app ships with
  none). Use games you are entitled to;
- for the Deck, SSH with a key (`deck@address:port` and the key in Settings).

### GitHub (required)

The first time, the page asks you to sign in with GitHub: it runs `gh auth login` and shows a code
to type at github.com/login/device (the app never sees your password). Your GitHub name is the
identity of the commits the assistant makes. Without a session only the sign-in page answers.

**Fixes are shared.** When the assistant fixes ReXNative for one of your games and the tests pass,
the app forks ReXNative into your account, pushes the commits to a branch there and opens a pull
request to ReXNative with the game, what the assistant found and the test results (never files from
the game). You keep the fix in your games right away; once the pull request is merged it reaches
everyone. Whoever can push to ReXNative directly (its maintainer) publishes to `main` instead.

### The AI assistant

Settings > "AI assistant" picks the one that fixes failures, investigates reports, compares
captures and picks covers (`gestor/agents.py`):

| Assistant | Sign in once | How the app runs it |
|---|---|---|
| Claude Code (`claude`) | `claude auth login` | `claude -p --input-format stream-json --output-format stream-json` (you can write to it while it works) |
| OpenAI Codex (`codex`) | `codex login` (ChatGPT account) | `codex exec --json` |
| Gemini CLI (`gemini`) | `gemini` > Sign in with Google, or `GEMINI_API_KEY` | `gemini --output-format stream-json` |
| Antigravity CLI (`agy`) | `agy` (Google account) | `agy -p ... --output-format stream-json` |
| Local model (Ollama or LM Studio) | nothing: start Ollama, `ollama pull gpt-oss:20b` and `ollama pull gemma3` | `codex exec --oss --local-provider ollama -m gpt-oss:20b` |

**Local model.** Nothing leaves the PC. The coding work goes through the Codex CLI in its open-source
mode (`npm i -g @openai/codex`; no OpenAI account needed), which drives a local model with tools
(`gpt-oss:20b` by default, Settings > "Model for fixing games"). Comparing captures and picking covers
needs a model that sees images (`gemma3` by default): the app asks the local server directly
(Ollama's `/api/chat` with the images and the JSON schema as `format`, or LM Studio's
`/v1/chat/completions`). Give Ollama a large context (`OLLAMA_CONTEXT_LENGTH=65536`): the fix
requests are long. Expect a local model to fix fewer games than the cloud ones.

Settings > "Test the assistant" checks the session. Claude Code is the one this app was built and
tested with; the others follow their documentation.

### Claude Code

The app uses the `claude` on the PATH, or the newest one the Claude app for Windows installed
(`%LOCALAPPDATA%\Claude-Data\...\claude-code\<version>\...\claude.exe`), or the path you give it.
The command-line version needs its own session (the Claude app's does not work), once, in
PowerShell (the `&` is needed to run a quoted path):

```powershell
& "<path to claude.exe>" auth login
```

The browser opens: authorize and, if PowerShell asks, paste the code the page shows.
Alternatively, `claude setup-token` and the result in `CLAUDE_CODE_OAUTH_TOKEN`. In Settings,
"Test Claude Code" confirms the session and "Fix self-test" proves the whole loop (a step that
fails on purpose in a separate folder, Claude fixes it with the cheapest model, the step passes;
nothing in ReXNative is touched).

Each fix runs as:

```
claude -p --output-format stream-json --verbose --permission-mode auto --permission-prompts none
       --no-session-persistence --add-dir <game folder> --add-dir <app logs>
```

in the ReXNative worktree used for builds (Settings: `rexnative_dir`), with the request on stdin:
the step that failed, the command, the end of the log (plus the crash report and a capture for
the boot test) and the repository rules (no game in the public repository, noreply identity on
commits, no local LLMs, do not touch the Deck or firewall dialogs, do not kill processes that are
not its own). The `auto` permission mode lets Claude work without questions but with Claude Code's
safety classifier; `--permission-prompts none` refuses on its own whatever would need a question.
This can be changed in Settings.

## How it is built

Python, because all the surrounding tools are Python (the `rexnative` package, the
`internetarchive` library, Pillow for the covers), and a local web page instead of a native app:
there is no build step and no UI dependencies, and long jobs (downloads, builds) keep running with
the page closed. The server (FastAPI) only listens on 127.0.0.1. Requests that change something
carry a header of their own, which a page from another site cannot send, and the `Host` has to be
the local one.

What is reused instead of rewritten:

| What for | What |
|---|---|
| Listing, downloading (resume, S3 authentication) and searching the Internet Archive | the [`internetarchive`](https://github.com/jjjake/internetarchive) library |
| Preparing, building, game title, Deck TOML files | the `rexnative` package (`prepare`, `project`, `deck.title_of`, `deck.toml_set`) |
| Installing on the Deck, Steam shortcuts and artwork | `python -m rexnative deck` and ReXNative's `deck/` kit (`steam_shortcuts.py`, `install.sh`, `play.sh`) |
| Boot test | ReXNative's `scripts/live.ps1` |
| Covers | the `fetch_covers.py` and `compose.py` scripts from an earlier session (XboxUnity, Marketplace), adapted; [SteamGridDB API v2](https://www.steamgriddb.com/api/v2) optional |

[Steam ROM Manager](https://github.com/SteamGridDB/steam-rom-manager) and NiceDeck were looked at:
they make shortcuts and artwork for emulators, but here the ReXNative kit already writes the
shortcuts the way `play.sh` needs them (no compatibility tool, with Steam closed and
`steam-launcher.service` masked in Game Mode), so the app uses it.

### XNA games

XNA games (the code is .NET, which the console compiles at runtime) do not run on ReXGlue, which
only runs code recompiled before launch. The app recognizes them without downloading them: it
reads the start of the STFS package inside the archive, over the network (`HostLoader.dll`,
`NetCFUserMode.dll`, `.xnb`; "check for XNA" in the catalogue, ~5 s per game, saved in
`catalog/xna.json`). In the catalogue they are marked "XNA (later)", with no download, and
preparation refuses them right away (without spending Claude).

## For later

- **XNA games via FNA:** Xenia and Xenia Canary do not run them either (all `crash-xna-WONTFIX`
  in the compatibility lists). The idea to investigate: extract the .NET assemblies from inside
  the XEX files (`game.exe.xex`, `MXF.*.dll.xex`) and run them with [FNA](https://fna-xna.github.io/)
  through [XnaToFna](https://github.com/0x0ade/XnaToFna), native on Windows and on the Deck
  (Linux). Test case: Dust: An Elysian Tail.

### The ReXNative copy

The app builds and fixes in a ReXNative copy of its own (`rexnative_dir`, by default
`~\ReXNativeManager\ReXNative`: a clone of ReXNative, or a worktree made with `git worktree add --detach
<folder> origin/main` with `ports.json` copied over). Other sessions work in other copies: in a shared folder, one
session's commits took the other's changes along and builds picked up half-done work. Before each
job the app moves it to the latest published `main`, if it has nothing uncommitted. Its status is
in Settings.

Each game shows its **contribution to ReXNative**: the commits that Claude's fixes (automatic or
from reports) left there, with a link to GitHub, what changed for all games, and what stayed only
in the game folder. Claude ends each fix with the `REXNATIVE:` and `COMMITS:` lines, and the app
counts only those commits (not those from other sessions in the same interval).

### Testing only the suspects

Testing every game on each change takes an hour. Claude ends each fix with a `SUSPECTS:` line:
the other games that go through the code that changed, seen in their logs and layers. The app
then queues a job that builds and tests only those, and says whether any got worse: the boot
failed, or one of its **test scenes** got worse. In Jobs, "Test games…" does the same for the games
you choose.

It is quick about it: the next game builds while one is being tested (the build is the processor's
work, the test the graphics card's; a build that fails there runs again in the game's Build step,
and if Claude changes the code mid-batch the rest build one at a time), and the boot test only
checks that the game starts (`boot_min_frames` and no crash, `quick_boot_seconds`, 20 s) instead
of the full minute, since the test scenes compare the picture. A game without its boot scene still
gets the full boot test once, to record it. Measured on a batch of six games: about 2.5 minutes a
game before (a build of 30 to 70 s, then a boot test of 68 s, then the scenes).

### Achievements

The ReXGlue SDK keeps a game's achievements: when the game unlocks one (`XGIUserWriteAchievements`)
it writes `userdata/achievements/<TitleID>.toml` (`[unlocked.<id>] filetime = N`) in the game's
folder, but its notification is drawn by the SDK's overlay, which the native renderer does not show.
The Manager shows them:

- **The list** comes from the game itself: the achievements table (`XACH`), the strings and the PNG
  icons of the title's SPA, the XDBF resource every title carries, read from the decrypted image
  `rexnative project` dumps (`run/image.bin`). Parsed once per build and cached in
  `data_dir/achievements/lists/`. A game built before the image was kept says to rebuild it.
- **The unlocked ones** come from the Deck (the listing the Manager already does over SSH reads each
  game's file, a few hundred bytes, also while a game runs) and from `run/userdata/achievements/`
  on this PC. What was read from the Deck stays in `data_dir/achievements/deck.json`, so the list
  shows them while the Deck sleeps; an unlock never disappears because a file could not be read.
- **Where:** the game page's **Achievements** tab on the PC (unlocked first, with the date and where);
  in Deck mode, the game sheet's line (`2 of 45 · 30 of 1000 G`) and **Achievements** button, a list
  the D-pad scrolls. Secret achievements (no "show unachieved" flag) show as "Secret achievement"
  with no icon until unlocked. When Deck mode opens after you played, it names the new ones.
- `GET /api/games/<slug>/achievements`, `.../achievements/icon/<image id>`, and the same under
  `/api/remote/achievements/` for Deck mode.

### Test scenes

A scene is a few frames of a game recorded as a ReXNative frame trace (what the game hands the
renderer and the guest memory it reads), with the pictures the build that recorded it drew (its
reference). After a ReXNative change the new build draws each scene again and the pictures are
compared pixel by pixel: the same frames, so a difference is the renderer's, never a slower start
or a fade caught at another moment (comparing captures taken at 15/30/45/60 s of two runs called
games "worse" for a black frame between an intro and the title). Equal pixels are "same" without
the model; a change gets a before/after picture with the changed region enlarged, and the cheap
model says whether it is better or worse. A better look becomes the reference (it can be undone);
any other change waits for **Accept the new look**.

Scenes come from the game itself: the boot test records one of where it ends, once per game;
**Save this scene as a test** (the game's Test scenes tab) records the next frames while you play it
with Play on this PC (the pictures are made when you close it); and Claude records the place of
each report (with the player's save) before fixing it, so that place is checked after every later
change. They live in `data_dir/scenes/<game>/`, a few MB each; a trace from a build whose command
structures changed is marked "needs recording again".

### Folders

| Folder | What it holds |
|---|---|
| `download_dir` (`~\ReXNativeManager\downloads`) | the downloaded archives, per item |
| `work_dir` (`~\ReXNativeManager\work`) | the games prepared by the app |
| `work_roots` | all the folders with games already prepared |
| `data_dir` (`~\ReXNativeManager\data`) | `jobs.json`, `state.json`, `logs/` (one log per job and per step, the Claude stream, and `server.log`), `covers/`, `shots/`, `backups/` (Deck saves), `catalog/` (metadata cache) |

The settings are kept in `config.json` next to the repository (outside git); the Settings page
writes it.

### Code

| File | |
|---|---|
| `gestor/app.py` | the API (FastAPI) and the page |
| `gestor/jobs.py` | background jobs, logs, cancelling (only the job's process tree) |
| `gestor/catalog.py` | Internet Archive sources, release names, search |
| `gestor/owngames.py` | your own games: the folders to look through, dumps, `.iso`, archives, Xbox Live packages |
| `gestor/worker.py` | the download in a separate process (cancellable) |
| `gestor/pipeline.py` | prepare / build / boot test and the loop with Claude |
| `gestor/claude.py` | the request to Claude Code and reading its stream |
| `gestor/deck.py` | the Steam Deck over SSH (and the shortcuts waiting for Steam to be closed) |
| `gestor/lan.py` | the app on the home network: devices, tokens, per-address servers |
| `gestor/orders.py` | Deck mode requests (download, prepare, build, send) |
| `gestor/catcovers.py` | catalogue covers by name (XboxUnity) |
| `gestor/deckapp.py`, `gestor/deckkit/` | the Manager on the Deck: shortcut artwork, launcher, installation |
| `gestor/static/deck.*` | the Deck mode page (controller, touch, keyboard) |
| `decky/` | the quick access menu plugin (Decky) |
| `gestor/covers.py` | finding and composing the covers |
| `gestor/games.py`, `state.py`, `config.py` | the prepared games, the app state, the settings |
| `gestor/static/` | the page (HTML, CSS and JavaScript, no framework) |

## Rules the app follows

- It only downloads what you choose; it only deletes (downloads, Deck games) when you press the
  button and confirm; before deleting a Deck game it offers a backup of the saves (`userdata/`,
  without the DLC, which gets reinstalled) and of the settings to `backups/`.
- It does not touch the Deck while someone is playing (`pgrep -af "[S]teamLaunch AppId="`), leaves
  nothing running there (no `systemd-inhibit`), and does not change the Deck's system settings.
- The boot test never closes a game that someone else opened with `live.ps1`: it waits.

## Contributing

Bug reports and pull requests are welcome: [CONTRIBUTING.md](CONTRIBUTING.md) says how, and what
must never be in this repository. Fixes to games go to ReXNative by themselves, as pull requests the
app opens. Security problems: [SECURITY.md](SECURITY.md).

## Licence

MIT ([LICENSE](LICENSE)), the same as ReXNative. Games, their files and the catalogue sources are not part of
this repository: use games you are entitled to.
