"""A versão da app e o que muda em cada uma.

Cada alteração que muda o que a app faz sobe VERSION (x.y.z: y para funções novas, z para
correções) e junta uma entrada a CHANGES, a mais recente primeiro; o commit leva a etiqueta git
vX.Y.Z. A app compara a versão que está a correr com a que está no disco (um commit novo, ainda
por reiniciar) e com a do GitHub (origin/main), e mostra o que muda (versions.py).

As versões do lançador do Deck (deckapp.VERSION) e do plugin do Decky (decky/package.json) são à
parte: a app sabe a que está no Deck e avisa quando há uma mais nova."""

VERSION = '1.34.2'

# (versão, data, [o que muda]) — em inglês, a língua da app.
CHANGES = [
    ('1.34.2', '2026-11-24', [
        "Screen scaling and FSR sharpening are the PC's only: the last step, the finished picture "
        "scaled up to a larger window with FSR 1, which never runs on the Deck (a 720p game is shown "
        "at its own size on its 1280x800 screen); the in-game menu hides them there too (ReXNative "
        "65e3321, after a rebuild). Their help says how they differ from the upscaler (FSR 4, DLSS, on "
        "the 3D scene) and that Resolution 2x/3x takes the upscaler up to the screen's size.",
    ]),
    ('1.34.1', '2026-11-24', [
        "The Deck no longer gets a PC's resolution scale, DLSS 5 or DLSS upscaler: Forza Horizon, set "
        "to 2x on the PC, came to the Deck at 2560x1440 with DLSS 5 tried and failing. The Deck's "
        "settings now always have 1x, DLSS 5 off and the upscaler automatic (FSR), and the renderer "
        "takes 1x on the Deck whatever the file says (ReXNative 60f5e96, 8ed5ee1).",
        "A game's Settings on the Deck shows Resolution, Upscaler type and DLSS 5 when the game "
        "has a PC's value for them there, so it can be taken back.",
    ]),
    ('1.34.0', '2026-11-24', [
        "A game's Settings on the Deck has what its settings menu in the game (Back + Start) has, "
        "with its Language first: renderer, screen (TV or PC monitor), frame rate, FPS limit, frame "
        "latency, antialiasing, screen scaling and FSR sharpening, texture filtering, FSR version, "
        "upscaler mode, frame generation, occlusion queries and log level. Each row shows what the "
        "game has now (the PC's settings with the Deck's), the one you focus is explained below, "
        "and only the rows you change are written, sent to the Deck in one go.",
        "The PC game page's Settings has them all too, for the PC's file and the Deck's, with the "
        "PC's own (window, window size, resolution 2x/3x, upscaler type, DLSS 5's look, intensity, "
        "speed, still hold and motion check), grouped as the HUD's pages, each Default saying what "
        "it is; and the Language, for the PC and the Deck together.",
        "Sem PC mode (Deck service 0.10.0): the same Settings, written in the installed game's own "
        "settings.",
    ]),
    ('1.33.1', '2026-11-24', [
        "Language: Português (Portugal) or Português (Brasil), as the game's own Portuguese texts are "
        "(tu and ecrã, or você and tela): Limbo, Castle Crashers, Spelunky, Super Meat Boy, Minecraft "
        "and 3D Ultra Minigolf are Portugal's; Forza Horizon, Darwinia, Peggle 2, Babel Rising, "
        "Brothers, Dark Souls II, Halo CEA and Orcs Must Die are Brazil's. A game whose data has both "
        "lists both, and the console's country follows the choice (Portugal or Brazil) so the game "
        "picks that one.",
        "A game's fonts no longer narrow its languages (Super Meat Boy's Chinese.fnt hid its "
        "European ones).",
    ]),
    ('1.33.0', '2026-11-24', [
        "Language: a game made in several languages plays in the one you pick, Português where "
        "the game has it (Limbo, Castle Crashers, Darwinia, Peggle 2, Forza Horizon, Babel Rising...): "
        "the list beside Store page on the game page, Language on the game's page on the Deck, also "
        "in Sem PC mode (Deck service 0.9.0). It goes to the PC and the Deck together and needs no "
        "rebuild; store pages list the languages.",
        "The list is the languages the game's achievement texts come in that its disc carries: "
        "Diablo III's European disc has English and French packs only, so Português is not offered "
        "there. Diablo III and Geometry Wars 3 ask the system for the language another way (ReXGlue "
        "SDK patch 0048): they follow the choice after a rebuild.",
    ]),
    ('1.32.0', '2026-11-24', [
        "More genres: each game's Wikipedia infobox adds what Wikidata and the store leave out "
        "(SSX: Sports and Snowboarding; 1037 genres more over the catalogue).",
        "The Deck's own games and the On the PC tab open as store pages too: the picture, genres, "
        "ratings, description, screenshots and play modes, with Play, Update or Rebuild at the "
        "top and the rest below.",
        "Store pages show the achievements (count and gamerscore) and a row of games like it from "
        "your catalogue; the PC catalogue and the Deck's sort by the players' rating (weighed by "
        "how many rated), and the covers show it.",
    ]),
    ('1.31.2', '2026-11-24', [
        "Store pages: a short name the store writes in capitals stays so (SSX, not \"Ssx\" from the "
        "file name, also on the Deck); HDTV without a resolution for the games read before 1.31.1 too.",
    ]),
    ('1.31.1', '2026-11-24', [
        "The Deck page comes back to its tab through its own address (#tab=) after an update; the "
        "store page shows HDTV without a resolution (the Marketplace's mode ids are not documented, "
        "and Dark Souls II read as 480p).",
    ]),
    ('1.31.0', '2026-11-24', [
        "Store pages: a game opens like a page of the Xbox store, on the PC and on the Deck (and in "
        "Sem PC mode): its background, box, genres, the players' rating and Metacritic, the "
        "description, screenshots, play modes and details, from Microsoft's own Xbox 360 "
        "Marketplace catalogue (no account or key) with Wikidata. Games have more than one genre "
        "now, in the lists too.",
        "The PC app looks new: the Deck app's colours and font, pill navigation, the catalogue in "
        "covers (or the list), and each game's page opens with its store picture, Play and the "
        "store page. The Steam Deck tab opens with the link at a glance: whether the Deck answers "
        "and since when, what waits for it, and whether its launcher and Decky plugin are the "
        "latest.",
        "PC and Deck work better together: a game that arrives after the Manager closed joins the "
        "library at once, and shortcuts left waiting are added when the Deck is free; opening the "
        "Manager during a transfer no longer holds the Deck's queue for up to 2 hours; Update and "
        "settings sent from the Deck wait for a sleeping Deck; a Deck that got a new address is "
        "found again; Play pressed long ago no longer starts a game later; the pairing screen no "
        "longer comes back on every launch; a retried request keeps the microSD card; the mode "
        "switch waits long enough and says when the PC cannot reach the Deck; errors say what "
        "happened instead of \"see the log\"; the PC and the Deck no longer restart Steam twice "
        "for the same shortcuts.",
    ]),
    ('1.30.2', '2026-11-24', [
        "The PC page and the Deck page reload themselves when the app updates: they went on "
        "running the old version's code until reloaded by hand, so new options (FPS Boost) did not "
        "show. The PC page comes back to the tab, game or job that was open, and waits while you "
        "type or have a dialog open; the Deck page comes back to its tab once no window is open. "
        "(A page opened before this version needs one reload by hand.)",
    ]),
    ('1.30.1', '2026-11-24', [
        "Deck mode: FPS Boost on the On the PC tab too (the game's sheet), with Rebuild (and send "
        "when the game is on the Deck).",
    ]),
    ('1.30.0', '2026-11-24', [
        "FPS Boost: a game's frame rate raised by Xenia canary's community patch (\"60 FPS\", "
        "\"Unlock FPS\"), as FPS Boost does on the newer Xboxes. The game page (Summary) and the "
        "game on the Deck page show it when there is a patch for the game's exact version, with its "
        "notes; On / Off is the game's choice, and nothing is built until you ask (Build and test "
        "on the PC, Rebuild and send on the Deck; Rebuild all applies it too). The build puts the "
        "patch into the game's code (ReXNative's fps-boost, ReXGlue's patch 0047). Iron Brigade "
        "went from 33 to 16.7 ms a frame; Fable II, Midnight Club LA, Blur, Asura's Wrath, The "
        "Bureau and Brothers have one too.",
    ]),
    ('1.29.4', '2026-11-23', [
        "Rebuild all on the Deck builds every game first and sends them after. It sent each game "
        "before building the next, so a Deck that went to sleep held the whole batch on the first "
        "send (overnight, one game of 23 was built). Now the PC builds them all, the sends wait "
        "in the queue, and they go one after the other when the Deck is back.",
    ]),
    ('1.29.3', '2026-11-23', [
        "Deck: a \"Just the crash log\" report waits for the Deck when it went to sleep after the "
        "report, and reads the crash log then. It went on without it, and Claude looked at an "
        "older crash from the PC's logs instead.",
    ]),
    ('1.29.2', '2026-11-23', [
        "Claude investigates the game stock first. When it looks into a problem, finds gameplay "
        "or checks a fix, it starts and replays the game with -Stock: without DLSS 5 and its "
        "look, the upscaler, the resolution scale, frame generation and the other extras the "
        "game's settings may turn on, so what it judges is the emulation. It turns one back on "
        "only when the problem is in it or shows only with it; a problem seen on the Deck is "
        "still tried with the Deck's settings, and a crash with the player's.",
    ]),
    ('1.29.1', '2026-11-23', [
        "\"Just the crash log\" (it was \"Only read the crash log\") no longer forbids opening the "
        "game. Claude starts from the crash log and opens the game when the fix needs it (to "
        "reproduce what the log does not hold, to find more missing functions, or to check the "
        "fix). Only the screenshot on the Deck stays off; your save and snapshots go with the "
        "report again.",
    ]),
    ('1.29.0', '2026-11-23', [
        "Report a problem has \"Only read the crash log\". Claude fixes a crash from the game's "
        "log alone (the crash report at its end: an unregistered function, a fault, the "
        "backtrace), and nothing opens, on the Deck or on the PC, to look. The fixed game is then "
        "built and started once to check it, and goes to the Deck. On the Deck the option comes "
        "ticked when the last time you played the game ended in a crash. On the PC it reads "
        "the PC's newest crash log; Without PC, the Deck's own Claude does the same.",
    ]),
    ('1.28.1', '2026-11-23', [
        "Tests compare the emulation, not the extras on top. The boot test's pictures, the "
        "native vs classic comparisons and the gameplay scenes now run without DLSS 5, the "
        "upscaler, the resolution scale, frame generation and forced anisotropic filtering, "
        "whatever the game's settings say: with DLSS 5's look on, the native picture differed "
        "from the classic one by the look, not by the emulation. The run with the Deck's settings "
        "keeps them.",
    ]),
    ('1.28.0', '2026-11-23', [
        "Rebuilds no longer open the game to test it. Rebuild, Rebuild outdated, Rebuild all on "
        "the Deck and a Rebuild asked from the Deck now only build (and resend to the Deck): the "
        "game passed its tests when it was made, and a build that fails still goes to Claude. No "
        "gameplay session starts after a rebuild either. A game's first build is still tested, "
        "and so is a report's fix. Settings > ReXNative > \"Rebuilds also open the game to test "
        "it\" brings the boot test back. Without PC, the Deck's own rebuilds work the same way.",
        "Deck: after \"Update\" on the \"newer launcher\" banner, the banner now goes away. It "
        "stayed until the Manager was closed (the page read the versions every 10 minutes). The "
        "PC also reads the launcher's version from the Deck itself, so a launcher installed "
        "without the PC no longer shows as old.",
    ]),
    ('1.27.9', '2026-11-23', [
        "Routes reach the game every time. The buttons a route presses (START, A...), the "
        "renderer switch of the comparisons and a scene's trace go to the game through a file it "
        "reads and removes at once; written a line at a time, it could be read empty, and the "
        "command was lost (a route stayed on the title screen). The file is now written whole. "
        "Games rebuilt with ReXNative from now on also wait for the file to be whole.",
    ]),
    ('1.27.8', '2026-11-23', [
        "Deck: after a mode change, the Manager stays in front. For the second between its old "
        "window closing and the new one opening, Steam put its own screen in front, and "
        "sometimes kept it there (a game's library page), with the Manager open behind it. "
        "Deck launcher v5 shows a dark window of the Manager over that second, so Steam "
        "keeps the Manager in front. The Manager asks you to update the launcher.",
    ]),
    ('1.27.7', '2026-11-23', [
        "Deck: changing the mode in Settings no longer takes the Manager down. Moving between "
        "the PC's Manager and the Deck's own (PC or Automatic from Without PC, or Without PC from "
        "the PC) froze the Deck's Firefox at times, and then it closed. Now the Manager closes "
        "and opens again by itself on the new side, in Settings. This needs Deck launcher v4: "
        "the Manager asks you to update it.",
    ]),
    ('1.27.6', '2026-11-23', [
        "Native vs classic: when the captures are the same pixels, the game is marked the same "
        "without asking the model. The model had called identical Marble Blast Ultra captures "
        "brighter. Otherwise the model now gets each pair's measured brightness, and calls the "
        "brightness different only past 0.02.",
        "Test scenes: a replay that leaves pictures empty now fails only that scene, with the "
        "reason, instead of the whole test (Limbo did). ReXNative 2ab2a9b writes every picture "
        "before a replay ends; rebuild a game to get it.",
        "Prepares on the PC are faster: the ReXGlue codegen now writes on every core "
        "(Iron Brigade 40.0 to 28.3 s per codegen run, the same files). This changes the SDK, so "
        "games show as built before it.",
    ]),
    ('1.27.5', '2026-11-23', [
        "Native vs classic comparisons no longer call the native picture brighter in games that "
        "darken it through the console's gamma ramp (Marble Blast Ultra, Limbo, Halo CEA, Castle "
        "Crashers). The native capture was the picture before the ramp, and the classic one after "
        "it. Checked frame by frame against the classic renderer, those four games showed the "
        "same picture.",
        "ReXNative a1b198b: captures can be taken as the screen shows them "
        "(--rexnative_capture_shown). The boot test and the Deck capture now ask for that. A game "
        "built before it ignores the option, so rebuild it to get a fair comparison.",
        "ReXNative 109d604 (with ReXGlue SDK patch 0043): Iron Brigade's title screen and menu "
        "panels no longer have grey blacks. Draws that blend into the console's gamma render "
        "targets stored the PC's sRGB values instead of the console's own. The title screen now "
        "matches the classic renderer (PSNR 26.5 to 51.1 dB). Rebuild a game to get it.",
    ]),
    ('1.27.4', '2026-11-22', [
        "Sem PC mode: a game whose prepare fails now stops at Prepare, and Claude looks at that step. "
        "ReXNative's prepare reported the failure in its table but ended as if it had worked, so the "
        "boot test failed with no build and Claude's step ended at once. Burnout Crash on the Deck "
        "failed like this.",
        "ReXNative 0975a2e: on the Deck, a game that names its executable DEFAULT.XEX (Burnout Crash) "
        "no longer fails its prepare at the title update step.",
    ]),
    ('1.27.3', '2026-11-22', [
        "Sem PC mode: downloads on the Deck are several times faster. archive.org gives one "
        "connection 0.5 to 1.5 MB/s, whatever the Wi-Fi (the Deck's did 780 Mbit/s), and three at "
        "once gave 3.7 MB/s. The Deck now downloads a game in 16 MB parts over 4 connections. A "
        "stopped download goes on with the parts it lacks, a part whose connection drops is asked "
        "again, and the MD5 is still checked at the end. Reconnecting one slow connection (1.24.2) "
        "did not help, because a new connection is no faster.",
    ]),
    ('1.27.2', '2026-11-22', [
        "Sem PC mode: games the Deck makes get their Steam artwork, as on the PC. A Covers step takes "
        "the box's official front from XboxUnity, the Xbox 360 Marketplace's background and its "
        "tile, and makes the library capsule, the wide capsule, the banner and the icon. A game "
        "already in the library gets them in Steam's grid folder, with no restart. Lazy Raiders, "
        "Limbo and Darwinia had none.",
    ]),
    ('1.27.1', '2026-11-22', [
        "Recipes carry a game's own headers too (src/game_*.h): Lazy Raiders' fix from the Deck "
        "(src/game_pch.h, with ReXNative d14acd5) now reaches the PC with its recipe.",
    ]),
    ('1.27.0', '2026-11-22', [
        "Sem PC mode: a game the PC built and sent is no longer just Play and Delete. Its Settings, "
        "Restore saves and Achievements work on the Deck, and its card shows its versions.",
        "Build on this Deck: a game the PC built is built again on the Deck. Its archive comes from "
        "the Deck's catalogue, and the PC's recipe makes the prepare shorter. It is installed over the "
        "PC's copy, keeping the saves and your settings. The page says first how long it takes and how "
        "much space it needs. Afterwards it is the Deck's game: Update, Rebuild and Report a problem "
        "work on it. If you use the PC again, the PC's next update of the game replaces that build.",
        "Report a problem on a game the PC built, in Sem PC mode, now offers to build it on the Deck "
        "first, instead of nothing.",
        "Move to the microSD card / Move to internal storage on every game on the Deck, with its saves. "
        "A game the PC built is copied as it is.",
        "Achievements of games the PC sends: ReXNative 7a44fae puts the game's achievements list "
        "(achievements.spa, a few hundred KB) in its Deck folder. Games sent before get it with their "
        "next update from the PC.",
    ]),
    ('1.26.0', '2026-11-22', [
        "Deck page, Settings: a new Accounts section with every sign-in of the Deck, one row each "
        "(archive.org, Claude, GitHub). Each row shows its state and has one button: Sign in, Sign "
        "out (it asks first) or Install.",
        "Signing in needs no typing where it can be avoided. GitHub shows its code big, and a QR code "
        "to scan with the phone; the page notices by itself when you are done. Claude shows a QR code; "
        "you type back the code its page gives you. archive.org takes the e-mail and password (or the "
        "S3 keys of an account that signs in with Google) on the page's keyboard, which now has "
        "capitals and symbols; the password shows as dots and is never kept.",
        "In PC mode, Settings has a button that opens the Deck's own accounts.",
        "Sem PC mode: a fix Claude makes to ReXNative on the Deck is now committed and pushed to main, "
        "as on the PC (signed in to GitHub on the Deck). If the push cannot happen, the commit stays "
        "on the Deck and is pushed before the next build. A report says \"committed and pushed (...)\" "
        "or \"committed here, not pushed (why)\".",
        "The Deck takes ReXNative's newest main before each build, so the PC and the Deck build the "
        "same code.",
        "With the GitHub sign-in, the Deck's updates and the shared recipes work without deploy keys.",
    ]),
    ('1.25.1', '2026-11-22', [
        "Sem PC mode: the boot test no longer fails a game that works when you play during it. "
        "While you play, the Deck's work stops, and the test counted that time as its own; it now "
        "counts only the time it runs.",
        "While you play, Claude's test game stops too (it went on in the background), and cancelling "
        "Claude's step now closes it.",
        "A full disk no longer leaves a request stuck as running and that queue dead until a restart: "
        "the request fails and the next one goes on. The Deck's page still answers on a full disk.",
        "Before a download and before a prepare the Deck checks its free space (as the PC does), and a "
        "full disk during a download says so at once instead of retrying for minutes.",
        "A prepare stopped half way (the battery, a cancel) no longer goes on from a half-extracted "
        "archive the next time (ReXNative e7b327a).",
        "When archive.org asks for the sign-in again, the Deck says how to sign in on the Deck.",
        "Deleting a game that did not finish installing on the microSD card removes it; moving a game "
        "to internal storage no longer puts it back on the card; a recipe that cannot be shared no "
        "longer fails an install that finished.",
        "One request a game: two asked at the same moment for one game can no longer both start.",
    ]),
    ('1.25.0', '2026-11-22', [
        "Sem PC mode: a game that fails while the Deck makes it goes to Claude, as on the PC. When "
        "Prepare, the build or the boot test fails, Claude on the Deck (signed in once) looks for the "
        "cause, fixes it, and the step runs again, twice at most per game. The fix stays on the Deck.",
        "A game the native renderer cannot start, with no fix, tries ReXGlue's classic renderer instead "
        "of failing, and starts on it from then on (the HUD, View + Menu, switches to the native one).",
        "On the Deck, two games ordered in the same second no longer write into one log.",
    ]),
    ('1.24.2', '2026-11-22', [
        "Sem PC mode: downloads on the Deck no longer stay slow. archive.org's transfer could fall to "
        "0.4 MB/s and stay there while a new connection did 2.3 to 3 MB/s (measured on the Deck). Like "
        "the PC since 1.17.2, the Deck now measures the speed every 20 s and, when it falls far below "
        "what the download had (or under 1 MB/s), opens a new connection from where it is. When new "
        "connections are no faster three times in a row, the line is just slow and it stops trying.",
    ]),
    ('1.24.1', '2026-11-22', [
        "Deck page: the pad moves one way at a time. Pressing down with the thumb a little to the side "
        "(the D-pad or the left stick) went down and sideways at once, so some games were hard to reach "
        "in the catalogue. Now the direction you hold wins until you let go, the stick follows only its "
        "stronger axis, and a diagonal pressed at once goes up or down.",
        "Held, the pad repeats a little slower (about 8 moves a second), so it stops where you want.",
        "One press seen twice (as the pad and as an arrow key) moves only once.",
    ]),
    ('1.24.0', '2026-11-22', [
        "Report a problem in the Sem PC mode: Claude on the Deck now debugs the way it does on the PC, "
        "with ReXNative's scripts/live.sh (live.ps1's commands on Linux and Proton): a live game kept "
        "running between experiments, frame captures with the Xenos renderer's image of the same frame "
        "beside them, the pad, the control file, frame traces recorded and played, compare, audit, idle "
        "and oracle. The game runs in a headless gamescope: never on the screen, muted, and never Steam "
        "or a game you play. Its own instructions for the Deck: the player's snapshot first, few "
        "rebuilds (5 to 7 minutes each there). Needs ReXNative 687f083 or later on the Deck.",
        "The Deck's kit gets a Python with numpy and Pillow for those scripts (compare, oracle).",
    ]),
    ('1.23.0', '2026-11-22', [
        'The Deck works without the PC: in the new Sem PC mode the Deck itself downloads, prepares, '
        'builds, tests and installs your games, with the same Manager page and Decky plugin. On the Deck, '
        'the new Settings tab chooses PC, Without PC or Automatic (the PC when it answers, the Deck when it '
        'does not). The Deck side lives in standalone/ (installed on the Deck with standalone/install.sh) '
        'and stays out of the public copy.',
        'Decky plugin 1.9.0 and Deck launcher 3 follow the mode; when the chosen side does not answer, the '
        'launcher offers the other one. Installing the Manager from the PC on a Deck set to work without '
        'the PC turns it to Automatic.',
    ]),
    ('1.22.0', '2026-11-21', [
        'Delete a game from this PC: on the game page, This PC copy, Delete from this PC. It removes the '
        'prepared and built game folder (its size is shown first), after a copy of the saves of this PC in '
        'backups/pc, and the downloaded file when you tick it. Your own dumps are never touched, the copy on '
        'the Deck stays as it is, and it refuses while the game is open or has jobs.',
    ]),
    ('1.21.1', '2026-11-21', [
        'The windows of the Manager tests say so in their title (for example "Blur - ReXNative Manager test '
        '(boot test): please do not play in this window"): the boot tests, the classic runs, the test '
        'scenes, and every live.ps1 window of the assistant. A player at the PC had taken a boot test for '
        'the game they had opened and set it to full screen while the test switched renderers and then '
        'closed it. Needs ReXNative 2b13ddd or later for the live.ps1 windows.',
    ]),
    ('1.21.0', '2026-11-21', [
        'Gameplay scenes: each game gets a test scene of real gameplay once. A short Claude session (Sonnet) '
        'starts the game, drives it with the pad until the player is playing, records the frames there, and '
        'looks at that spot on the native and the classic renderer (a native one wrong there sends a report). '
        'A new game gets it in a job of its own after its pipeline, so the transfer to the Deck does not wait; '
        'a game in a suspects batch gets it first, with the build from before the change, so the same batch '
        'already compares real gameplay. Castle Crashers: the opening barn, in 4 minutes.',
        'With a gameplay scene a rebuild or update boots for 20 s, the comparison of captures at 15/30/45/60 s '
        'is left out, and the test with the Deck settings draws the gameplay scene with them (seconds, the same '
        'frames on both sides) instead of a minute of the game.',
    ]),
    ('1.20.3', '2026-11-21', [
        'Report a problem (on the PC) shows the snapshots you took on this PC in the last day (the settings '
        'menu, then Y), with their picture: the ticked ones go with the report, and you can untick one that '
        'shows something else. Before, they went along without showing in the dialog.',
    ]),
    ('1.20.2', '2026-11-21', [
        'A test scene that makes the game crash no longer holds a batch for 4 minutes: the scene is played '
        'while its log is read, and a crash (or a fault the renderer caught) ends it at once. Such a scene is '
        'then skipped until the renderer changes. The boot scenes of Tetris Splash and Double Dragon Neon '
        'crashed this way; ReXNative 4478eb3 fixes the cause (a played trace now reads the textures it did '
        'not record), and both scenes play.',
        'The app no longer locks itself after reopening when GitHub takes long to answer: a check of the '
        'session that runs out of time uses the last session known, as without internet. It locked the whole '
        'app until the next check, five minutes later.',
    ]),
    ('1.20.1', '2026-11-21', [
        'Decky plugin 1.8.0: the panel now starts with what the PC is doing (the job it is working on and '
        'for how long, how many wait, a pending restart), and each request shows its stage, a progress bar '
        'and the time left. A request that waits says what it is waiting for, and while Claude fixes a '
        'failed step the panel says so instead of showing the command. A failed request shows in red with '
        'its reason, and pressing A on any request opens its full details.',
        'Decky plugin: when the PC does not answer, the panel keeps the last state for a moment and then '
        'says why (PC off, Deck not paired, network refused, sign-in missing); the games played last keep '
        'their Play buttons with the PC off, and the number of requests in progress shows beside the title '
        'and as a dot on the plugin icon. It asks the PC less often: not every 3 seconds while the menu is '
        'hidden, and once a minute while the PC does not answer. Update it from Deck mode (What is new) or '
        'from the plugin panel.',
        'What the PC is doing (Deck mode and the plugin) counts a download and a transfer to the Deck as '
        'work: it said the PC was free during them.',
        'The requests list of Deck mode always has every request in progress: one still running behind 40 '
        'newer ones dropped out of it. A failed download says what the downloader said last, as plain text. '
        'The strip of the request in progress also says "Claude is fixing" for a rebuild asked from the Deck.',
    ]),
    ('1.20.0', '2026-11-21', [
        'New games are prepared in a lane of their own, beside the builds. A pipeline that starts from an '
        'archive (Prepare: extraction, code generation, the first builds, then its tests and any fixes) runs '
        'in the prepare lane, in a third copy of ReXNative that only it uses (made the first time, named '
        '...-prepare). The builds, tests and reports of the games you already have no longer wait for it: '
        'one prepare of 98 minutes had held 5 pipelines, 2 reports and a batch. New games still go one at a '
        'time, only one game is on the test bench at a time, and an SDK update waits for the lane and keeps '
        'it closed. Settings: prepare_lane (off puts new games back in the build lane).',
        'Deck mode and the Decky data say what the prepare lane is doing too (what the PC is working on).',
    ]),
    ('1.19.1', '2026-11-21', [
        'Deck mode: while the assistant fixes a step, the strip of the request in progress says so in a few '
        'words instead of showing the command it is running (the details stay in Requests).',
    ]),
    ('1.19.0', '2026-11-21', [
        'Deck mode, L2 and R2 jump in the game grids: to the previous or the next letter in a list sorted '
        'by name (the letter shows in the middle of the screen; hold the trigger for letter after letter), '
        'and three rows at a time in any other order. With about 2000 games in the catalogue the D-pad alone '
        'took minutes. On a keyboard: [ and ], or Home and End.',
        'Deck mode shows the request in progress on every tab: a strip under the top bar with the game, the '
        'stage and the progress (and how many more wait); touch it to open Requests.',
        'Requests says what the PC is doing now: the jobs running in the build lane and in the report lane, '
        'for how long, how many wait, and a pending restart. A request that waits shows what for.',
        'Deck mode opens on the tab it was left on.',
        'The top bar of Deck mode no longer breaks: the tabs stay on one line and the status gives way (a '
        'warning in it pushed On Deck and On PC onto two lines); the warning that the PC cannot reach the '
        'Deck is a short chip.',
    ]),
    ('1.18.2', '2026-11-21', [
        'The Prepare step says where its time went: "prepared and built in 88 s (codegen 6 s in 4, build '
        '59 s in 2, game 3 s in 1)", the seconds and the number of codegen runs, builds and runs of the '
        'game, from the line ReXNative now ends each prepare with. A slow prepare can be read from the job '
        'itself (the 98 minutes of one were 33 codegen runs, found only by counting lines).',
    ]),
    ('1.18.1', '2026-11-21', [
        'Downloads on a line that drops now and then finish: a dropped connection that had brought data '
        '(8 MB or more) no longer counts as a failed try. The five tries are of drops in a row that bring '
        'nothing. Before, any five drops ended the download, however far each one got.',
        'scripts/test_download.py tests the download worker with a made-up connection.',
    ]),
    ('1.18.0', '2026-11-21', [
        'The app restarts between jobs, and the queue comes back. A restart (after an update, or Restart) '
        'now waits only for the jobs that are running: the queued ones stay queued and continue when the app '
        'is back, in the same order. Before, it waited for the whole queue to empty, which took hours with '
        'requests coming in (one restart waited from 17:04 into the night). Requests from the Deck, a '
        'download and a transfer that waits for a sleeping Deck do not hold a restart either: they give '
        'their turn back and pick up where they were. Closing the app with jobs queued no longer loses '
        'them: they are back in the queue the next time it opens (the job that was running is marked '
        'interrupted, as before).',
        'Reports have a lane of their own. Claude investigates a report beside whatever the build lane is '
        'doing, in a second copy of ReXNative that only reports use (made the first time, next to the '
        'other one, named ...-reports), with its own live game. Before, a report waited behind every '
        'pipeline and every other job (up to 62 minutes, measured), and a long report held every build '
        '(44 minutes). One job at a time still works on a given game, the test bench still runs one game at '
        'a time, and an SDK update waits for the report lane and keeps it closed. A fix that could not be '
        'published (someone who cannot push to ReXNative) is brought from one copy to the other before the '
        'next job, so both lanes build the same code. Settings: report_lane (off puts reports back in the '
        'build lane).',
        'scripts/test_jobs.py tests the queue with made-up jobs (lanes, restart, the queue after it, one '
        'job per game).',
    ]),
    ('1.17.3', '2026-11-21', [
        'Clear the job list: in Jobs, Clear failed (failed, cancelled and interrupted jobs) and Clear finished '
        '(every finished job); in Deck mode, Clear finished in Requests. Queued and running jobs stay, and the '
        'logs of the cleared ones stay in the logs folder.',
    ]),
    ('1.17.2', '2026-11-21', [
        'Downloads that got slow after the network went down recover: the download measures its speed and, '
        'when it falls far below what it had (or under 0.6 MB/s), opens a new connection from where it is, '
        'often to another server of the Internet Archive. Before, a connection left slow went on at a tenth '
        'of the speed to the end. When new connections are no faster three times in a row, the line is just '
        'slow and it stops trying.',
    ]),
    ('1.17.1', '2026-11-21', [
        'Reports with a snapshot: what Claude is told now opens with the snapshot, beside your description '
        '(its picture first, then its trace), and its first step is to play that trace on the PC and set it '
        'beside the picture, instead of reaching the place: wrong the same way, it fixes on that trace; right '
        'on the PC, it plays it with the settings of the Deck (a path of one setting) or reasons about the '
        'GPU of the Deck. It reaches the place live only for what a trace does not hold, and when it cannot reach a place '
        'without a snapshot it asks you for one (View + Menu, then Y).',
    ]),
    ('1.17.0', '2026-11-21', [
        'Snapshots for reports: at the place, in the game, open the settings menu (View + Menu on the Deck) '
        'and press Y. ReXNative saves that moment: the picture as shown and a trace of the next frames. A '
        'report from Deck mode sends the newest ones ("Send the snapshots you took", on by default), and '
        'Claude looks at the picture and replays those exact frames on the PC first, with no place to reach. '
        'Deck mode shows them on the game\'s sheet and says when a new one was taken. Games get the menu\'s Y '
        'when they are rebuilt (ReXNative after this change).',
        'Testing the suspects of a fix is faster: the next game builds while one is being tested, and the '
        'boot test only checks that the game starts (20 s, not a minute: the test scenes compare the '
        'picture). A game without its boot scene still gets the full boot test once, to record it.',
    ]),
    ('1.16.0', '2026-11-21', [
        'Reports, faster: what Claude is told when it investigates a report was rewritten from where the '
        'last reports spent their time (up to an hour: reaching the place again after every rebuild, '
        'minutes of blind waiting, searching the recompiled game). Now it reaches the place once, records '
        'a frame trace there at once and, after each rebuild, plays that trace (about 20 s) instead of '
        'reaching the place again; it sorts the fault with the new ReXNative tools (the Xenos renderer at '
        'the same spot, Oracle, compare, audit, idle, RenderDoc summary) before reading code, and gets '
        'the game\'s test scenes to play at once.',
        'The old comparison of captures at 15/30/45/60 s (intros) is no longer in a report: it misled one '
        '(The Bureau\'s "scrambled subtitle" was the game\'s own animation).',
        'Claude\'s live game has a state folder of its own: another session\'s game is never in its way, '
        'and the app closes the one it left running.',
    ]),
    ('1.15.0', '2026-11-21', [
        'Achievements: every game\'s Xbox 360 achievements, with the ones you unlocked. The ReXGlue SDK '
        'already saved them when a game gave one, but its notification does not show with the native '
        'renderer, so nobody saw them. The list, texts and icons come from the game itself (its SPA); '
        'the unlocked ones from the Deck (read with the listing the Manager already does) and from '
        'playing on this PC. On the PC: the game page, tab Achievements. In Deck mode: the game sheet '
        'shows "2 of 45 · 30 of 1000 G" and an Achievements button, and opening the Manager after '
        'playing names the new ones. Secret achievements stay hidden until unlocked.',
    ]),
    ('1.14.0', '2026-11-21', [
        'A request that waits says what for: builds and Claude fixes run one at a time on the PC, so a '
        'report or install made while another one runs now shows "Waiting for the PC to finish Report: '
        'The Bureau (running for 40 min)" in Deck mode (and "waits for ..." in Jobs on the PC), not '
        '"Claude is investigating" while it is still in the queue.',
        'The SDK no longer shows official commits as new when they change no file (the official '
        '"Release vX" commits only mark a version): Update and rebuild the SDK appears only for real changes.',
        'Server log: what the app writes to its console (errors, thread tracebacks, warnings) also goes '
        'to logs/server.log, with the time; after a restart the app runs hidden, and errors were lost. '
        'The version window links to it.',
    ]),
    ('1.13.0', '2026-11-21', [
        'Test scenes, so "got worse" means it: a scene is a few frames of a game recorded as a ReXNative '
        'frame trace, with the pictures its build drew. After a ReXNative change the new build draws '
        'each scene again and the pixels are compared: the same frames, so a slower start or a fade can '
        'no longer look like a fault. A change gets a before/after picture (the region enlarged) and the '
        'model says better or worse; a better look becomes the reference (Undo), others wait for Accept.',
        'Scenes from the game itself: Save this scene as a test while you play on the PC (the game page, '
        'Test scenes), the place of each report (Claude records it), and where the boot test ends.',
        'Testing the suspects of a fix: built, booted and their scenes checked. The comparison of captures '
        'at 15/30/45/60 s of two runs no longer decides (it called The Bureau and Brothers worse for a '
        'black frame between an intro and the title).',
    ]),
    ('1.12.0', '2026-11-21', [
        'Talk to the assistant: open a request (Deck mode, Requests) or a job (PC) to follow what Claude, '
        'or the assistant chosen in Settings, says and does, live; while Claude works you can write to '
        'it (X and the on-screen keyboard on the Deck, a box on the PC) and it reads the message in what '
        'it is doing.',
        'Report a problem from the Deck: "Send my save" (on by default) copies the game saves from the '
        'Deck into the PC copy, so Claude plays from your progress and reaches menus a new game does not '
        'have. The saves the PC had are kept in backups/pc; the Deck save is not changed.',
    ]),
    ('1.11.2', '2026-11-21', [
        'Play on this PC: the keyboard works as a controller (Enter Start, Space A, W A S D move, arrows '
        'look; the keys are on the game page), beside any controller. Without a controller connected the '
        'game had no controls at all. Play also says when the PC has no controller connected.',
    ]),
    ('1.11.1', '2026-11-20', [
        'Restart and Update from GitHub refuse to restart when the code on disk does not compile (and '
        'say where): restarting with a broken file left the app down until it was opened by hand.',
    ]),
    ('1.11.0', '2026-11-20', [
        'Play from the PC app: "Play on this PC" on the game page and a Play button on each game card '
        '(it starts the built game with the PC settings; a second press says it is already open), and '
        '"Play on the Deck" for a game in the Steam library of the Deck (as Play in Deck mode).',
    ]),
    ('1.10.0', '2026-11-20', [
        'Your own games, as you have them: a dump in a folder (with default.xex), a disc image (.iso), '
        'an archive (.7z, .zip, .rar) or an Xbox Live package. "Add your own game…" (My games, '
        'Catalogue) takes one, typed in or chosen in a Windows window, says what it found, and '
        'prepares, builds and tests it.',
        'Your game folders (Settings, or "Add it to your game folders"): the app looks through them '
        'and their games show in the catalogue as "Your files", on the PC and in Deck mode, where '
        'Install goes straight to preparing from your file, with no download.',
    ]),
    ('1.9.0', '2026-11-20', [
        'Changelog, a new tab in the PC app and in Deck mode: every ReXNative change on main by day, '
        'with its area (renderer, upscaling and frame generation, SDK, porting tool, Steam Deck, '
        'debugging, docs) and the games it names; open one for its whole description and files.',
        'Each game it names shows whether your build has it: on the Deck, built on the PC (update '
        'the Deck), or not built in yet (rebuild). Choose a game to see what mentions it, or what its '
        'Deck or PC build still lacks; the side panel (PC) and the game list (Deck) say how far behind '
        'each of your games is.',
        'New changes since you last looked are marked, with a count on the tab; the branches on '
        'GitHub with work not in main yet (vulkan-experiment) are shown apart.',
        'The Jobs counter at the top no longer shows a 0.',
    ]),
    ('1.8.0', '2026-11-20', [
        'Linux builds, experimental and on request per game: Build for Linux (in WSL, with the Linux '
        'tools of ReXNative), send it to the Deck beside the Windows build, and choose which one the '
        'Steam shortcut starts. Native, no Proton, drawn by the ReXGlue renderer on Vulkan: it uses '
        'far more GPU than ReXNative, so the Windows build stays the default.',
    ]),
    ('1.7.0', '2026-11-20', [
        'A local model as the assistant (Settings > AI assistant > local): Ollama or LM Studio, nothing '
        'leaves the PC. The Codex CLI in its open-source mode drives a coding model with tools '
        '(gpt-oss:20b by default); comparing captures and picking covers ask a model that sees images '
        '(gemma3 by default) straight on the local server. Test the assistant says what is missing.',
    ]),
    ('1.6.0', '2026-11-20', [
        'Signing in with GitHub is required (the GitHub CLI: a code to type at github.com, the app never '
        'sees the password); the commits the assistant makes carry your GitHub name.',
        'Fixes are shared: when the assistant fixes ReXNative for a game of someone who cannot push to '
        'it, the app forks it into their account and opens a pull request with the game, what was found '
        'and the tests.',
        'Choose the AI assistant: Claude Code, OpenAI Codex (with a ChatGPT account), Gemini CLI or '
        'Antigravity CLI (Settings > AI assistant).',
        'Ready to be public: no game sources, paths, addresses or names of this PC in the code (they '
        'live in config.json); the app clones ReXNative itself the first time.',
    ]),
    ('1.5.0', '2026-11-20', [
        'Play: from a Deck game in Deck mode (the Manager closes and the PC starts the game through '
        'Steam) and from the Decky plugin (1.7: the games played last, one button each).',
        'Deck mode: search and sort in On Deck (name, last played, size, recently sent) and On PC '
        '(name, recently built, Metacritic); Free space lists the Deck games from the biggest, with '
        'when each was last played, to delete several at once (saves copied to the PC first).',
        'What ReXNative tunes for each game (from its generated layer and its settings), on the game '
        'card, the On PC sheet and the PC game page.',
        'PC app: a Compatibility page (every game, its tests, renderer, XDK; sortable, CSV) and a '
        'Storage page (each game folder by parts, the downloaded archives, delete the ones already '
        'prepared).',
        'ReXGlue SDK in the settings: the installed version, our changes on top of the official SDK, '
        'what is new there (releases and nightlies), and Update and rebuild the SDK.',
    ]),
    ('1.4.1', '2026-11-20', [
        'Games with no cover found get a generic one in the style of an Xbox 360 case (the green band '
        'with XBOX 360 or XBOX LIVE ARCADE, a green emblem with an X, the name of the game) instead of '
        'a plain square; the real cover replaces it when it is found.',
    ]),
    ('1.4.0', '2026-11-20', [
        'Deck mode: a new tab, On PC, with the games prepared on the PC: covers, what is on the Deck, '
        'what is not built or lacks the latest fixes, the test results, filters; install one on the '
        'Deck (internal storage or microSD), build or rebuild it.',
    ]),
    ('1.3.0', '2026-11-20', [
        'Update all and Rebuild all, in Deck mode (On your Deck) and in the PC app (Steam Deck): one '
        'job that goes through the games one after the other, one line in Requests and one notice at '
        'the end.',
        'Notices: requests that finish together make one notice, and the Decky plugin (1.6) stays '
        'quiet while the Manager is open on the Deck (it already shows its own: they came twice).',
    ]),
    ('1.2.6', '2026-11-20', [
        'Decky plugin 1.5: requests with the name of the game (not its folder) and what they are; '
        'the text wraps instead of being cut, the progress bar sits under it, and the rows take the '
        'focus so the D-pad scrolls down the panel.',
    ]),
    ('1.2.5', '2026-11-20', [
        'Decky plugin 1.4.4: 1.4.3 lost the function that reads the address of the PC and the token, '
        'so it always said it was not connected. Packaging the plugin now checks main.py first.',
    ]),
    ('1.2.4', '2026-11-20', [
        'Game cards in Deck mode showed no versions or fixes since 1.0.0 (an error from the clean-up '
        'in the review): fixed.',
        'What each version fixes is saved when it is sent to the Deck (and once for the older sends), '
        'and the list of ReXNative commits is kept on disk: the card no longer asks git each time.',
        'Deck mode keeps each game card and opens it at once with what it had, then updates it if '
        'something changed.',
    ]),
    ('1.2.3', '2026-11-20', [
        'Catalogue covers: two thirds were missing. A network hiccup while fetching was recorded as '
        '"no cover" for 7 days; now only a real "not found" is, and the old marks are looked up again.',
        'Covers matched better: notes like "(Xbox 360)" ignored, abbreviations read as the words of '
        'the title ("GTA", "LA", "HBP"), a different sequel number is a different game.',
        'Without a cover on XboxUnity: the Xbox marketplace box art, then the Wikipedia image of the game '
        '(slowly: Wikimedia refuses many requests in a row). Covers are looked up again every 6 hours.',
    ]),
    ('1.2.2', '2026-11-20', [
        'Decky plugin install: Decky 3.3 sends its install request as message type 5; the request '
        'now recognises it (plugin 1.4.3).',
    ]),
    ('1.2.1', '2026-11-20', [
        'Installing or updating the Decky plugin works: Decky keeps one connection to its API at a '
        'time, so its "install?" window went to the request instead of the Deck screen and never '
        'showed. The button you pressed is the choice: the request now confirms it and Decky '
        'installs and reloads the plugin (plugin 1.4.2, which asks you first in its own panel).',
    ]),
    ('1.2.0', '2026-11-20', [
        'The Decky plugin goes to ~/Downloads on the Deck and Decky asks there to install or update '
        'it (confirm on the Deck): a button in the PC app (Settings > Deck mode) and in Deck mode.',
        'Decky plugin 1.4: an "Update the plugin" button in the quick access menu when the PC has a '
        'newer one. Each version goes to its own file (gestor-rexnative-decky-<version>.zip), so an '
        'install waiting for confirmation is never broken by a newer copy.',
    ]),
    ('1.1.0', '2026-11-20', [
        'App versions: the version in the PC app and in Deck mode, what changed in each one, a notice '
        'when a newer one is on the PC or on GitHub, and Update / Restart when no job is running.',
        'The Deck launcher and the Decky plugin say which version is on the Deck; Deck mode can update '
        'the launcher.',
        'Deck mode: install to the microSD card, restore a backup of the saves, a request sheet that '
        'keeps updating, faster D-pad moves in long grids, one on-screen keyboard.',
        'Boot test: the classic renderer captured in the same run as the native one (the renderer '
        'switch), so native and classic show the same moment; the second run only when that fails.',
        'Captures taken by the app itself (no PowerShell per capture); game logs read incrementally.',
        'Deck: one SSH call checks it is awake, whether a game is open, and lists the games; only the '
        'game that changed is measured after a send; a report collects the Deck files in one go.',
        'Steam on the Deck is not closed when a game started in the meantime (also in ReXNative, 5226a5a).',
        'Deck mode says when the PC cannot reach the Deck over SSH (sending then waits).',
        'A home network in 172.16-31 is no longer mistaken for a virtual one.',
        'Fewer duplicates in the code; jobs for the same game or file cannot start twice.',
    ]),
    ('1.0.0', '2026-11-20', [
        'Catalogue of the Internet Archive sources and search, downloads with resume and MD5.',
        'Prepare, build and boot test on the PC; native / classic comparison; test with the Deck '
        'settings; Claude fixes failures and investigates reports.',
        'Steam Deck: install, update, delete with a backup, settings, covers, the library.',
        'Deck mode on the Deck with the controller, requests from download to library, reports '
        'from the Deck, each game\'s versions and fixes; Decky plugin.',
        'Classic renderer instead of an error when the native one fails and no fix is found.',
        'General review: much faster pages, safer file writes and Deck jobs.',
    ]),
]


def parse(text):
    """VERSION e CHANGES de um version.py (o do disco ou o do GitHub), sem o importar."""
    import ast
    out = {'version': None, 'changes': []}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ('VERSION', 'CHANGES'):
                try:
                    out[name.lower() if name == 'VERSION' else 'changes'] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return out


def key(v):
    """'1.10.2' -> (1, 10, 2), para comparar."""
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except ValueError:
        return (0,)
