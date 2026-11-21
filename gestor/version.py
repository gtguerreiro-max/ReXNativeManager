"""A versão da app e o que muda em cada uma.

Cada alteração que muda o que a app faz sobe VERSION (x.y.z: y para funções novas, z para
correções) e junta uma entrada a CHANGES, a mais recente primeiro; o commit leva a etiqueta git
vX.Y.Z. A app compara a versão que está a correr com a que está no disco (um commit novo, ainda
por reiniciar) e com a do GitHub (origin/main), e mostra o que muda (versions.py).

As versões do lançador do Deck (deckapp.VERSION) e do plugin do Decky (decky/package.json) são à
parte: a app sabe a que está no Deck e avisa quando há uma mais nova."""

VERSION = '1.17.2'

# (versão, data, [o que muda]) — em inglês, a língua da app.
CHANGES = [
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
