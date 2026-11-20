# Security policy

## Supported versions

Only the latest version on `main` is supported (the version is at the top of the app's page);
there are no older branches to back-port fixes to.

## Reporting a vulnerability

Please do **not** open a public issue. Report it privately through GitHub: the repository's
**Security** tab, **Report a vulnerability**
([GitHub's guide](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)).
Say what is affected, how to reproduce it, and what an attacker could do with it.

This is a one-person spare-time project: expect an answer within a couple of weeks. Once it is
fixed, the report can be published as a GitHub security advisory, with credit to you if you want
it.

## Scope

In scope:

- the app (`gestor/`): the local server on `127.0.0.1:8360` (its checks on the Host header and the
  `X-Gestor` header), Deck mode on the home network (pairing, the device tokens, what a paired
  device can reach), downloads and archive extraction, and how it runs the AI assistant and the
  GitHub CLI;
- what it puts on the Steam Deck: the launcher (`gestor/deckkit/`), the SSH jobs and the Decky
  plugin (`decky/`);
- the scripts (`scripts/`, `iniciar.bat`).

Out of scope, to be reported to their own projects: ReXNative and the ReXGlue SDK, the AI
assistants' command-line tools, the GitHub CLI, Decky Loader, Steam and Proton, and the games.
