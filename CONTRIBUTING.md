# Contributing to ReXNative Manager

Thanks for your interest. The Manager is a small project kept by one person in their spare time,
so reports that are easy to reproduce and pull requests that do one thing are the most help.

## Fixes to games go to ReXNative by themselves

When the AI assistant fixes ReXNative for one of your games and the tests pass, the app forks
ReXNative into your GitHub account and opens a pull request there, with the game, what was found
and the test results. You do not need to do anything for those: this repository is for the app
itself.

## The one hard rule: nothing from a game, and no game sources

This repository must never hold:

- anything from a game: game files, saves, captures or covers of a game, generated code, a game's
  layer, or listings of a game's files;
- catalogue sources: the app ships with none, and each user adds the ones they want in Settings
  (they live in `config.json`, which is not in git). Do not add any to `gestor/config.py`;
- anything from your own setup: paths, addresses of your network, the name of your PC, keys or
  tokens. Those go in `config.json` too.

A pull request that adds any of the above is closed, and the content removed from history if it
was pushed.

## Reporting a bug

Open an issue with the **Bug report** form: what you did, what happened, what you expected, the
app's version (at the top of the page), and the job's log if a job failed (Jobs, open the job).
A game that does not build or draw right is a ReXNative problem: the app's **Report a problem**
investigates it with the assistant, or use ReXNative's **Game report** form. For a security
problem, read [SECURITY.md](SECURITY.md) instead.

## Pull requests

1. Open an issue first for anything bigger than a fix, so we can agree on the approach before you
   spend time on it.
2. Run the app with your change (`iniciar.bat`) and try what it touches: the page on the PC, Deck
   mode (`/deck`, 1280x800, with a controller or the keyboard), or the Decky plugin. Say in the
   pull request what you tried, and where.
3. The app has no framework on the page (`gestor/static/`: plain JavaScript and CSS) and few Python
   dependencies (FastAPI and uvicorn): keep it that way. Code follows the style of the file
   around it; the interface is in English.
4. A change in what the app does raises `VERSION` in `gestor/version.py` and adds a line to
   `CHANGES` (x.y.z: y for features, z for fixes); the Deck launcher (`deckapp.VERSION`) and the
   Decky plugin (`decky/package.json`) have their own versions.
5. Update the README where the change shows.

By contributing you agree to license your contribution under the project's [MIT License](LICENSE).
