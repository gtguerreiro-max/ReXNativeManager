"""A versão da app e o que muda em cada uma.

Cada alteração que muda o que a app faz sobe VERSION (x.y.z: y para funções novas, z para
correções) e junta uma entrada a CHANGES, a mais recente primeiro; o commit leva a etiqueta git
vX.Y.Z. A app compara a versão que está a correr com a que está no disco (um commit novo, ainda
por reiniciar) e com a do GitHub (origin/main), e mostra o que muda (versions.py).

As versões do lançador do Deck (deckapp.VERSION) e do plugin do Decky (decky/package.json) são à
parte: a app sabe a que está no Deck e avisa quando há uma mais nova."""

VERSION = '1.12.0'

# (versão, data, [o que muda]) — em inglês, a língua da app.
CHANGES = [
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
