# Security

Positronic Bond Engine is a solo-maintainer, pre-1.0, actively-developed
project. There is no formal vulnerability-disclosure program, no bug bounty,
and no third-party security audit or certification of any kind. Treat this
repository accordingly.

## Current baseline

- Branch protection was enabled on `main` on 2026-08-23: force-pushes and
  branch deletion are blocked (including for the repo's own admin), and
  changes go through a pull request. No CI/status checks are required
  today because none exist yet.
- No commit-signing requirement is configured or enforced.

This is the current state, not a target or a promise of what it will become.

## Reporting a security concern

Open a GitHub issue on this repository. There is no dedicated security
contact or private disclosure channel set up yet — for anything sensitive
enough that you don't want it public before a fix exists, say so in the
issue and the maintainer will follow up on how to share detail privately.

There is no guaranteed response time.
