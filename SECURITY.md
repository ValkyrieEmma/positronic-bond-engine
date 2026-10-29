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

## Verified, read-only ethics core

The ethics/ontology data the governor loads lives in `core/ethics_core/`
(today: `ontology_vocabulary.json`). It is protected as follows:

- **Verified at load.** `core/verified_core.py` checks the whole directory
  against sha256 digests pinned in code (`core/ethics_core_manifest.py`)
  before any byte is parsed. The bytes that were hashed are the bytes that
  get parsed.
- **Fail closed.** A missing, extra, modified or unreadable file (or an
  empty manifest) refuses the load: `get_default_ontology()` and
  `EthicsEngine()` raise, and `core.action_authorization.authorize()` denies
  every action, speech or physical, with `failure="core_integrity"` in the
  audit log, even if the gate itself would have allowed it.
- **Read-only at runtime.** No runtime code path writes to the core (a test
  scans for write calls). The loaded data is immutable in memory
  (`MappingProxyType` and tuples; `EthicalPrinciple` and `EthicalOntology`
  are frozen).
- **No runtime override.** No environment variable, config key, CLI flag or
  argument can point the loader elsewhere or skip verification.

### Changing the ethics core (human developer step)

1. Edit the file under `core/ethics_core/` (for the vocabulary, also bump
   `vocabulary_version` / `principles_hash` as before).
2. Run `python scripts/rebuild_ethics_manifest.py`.
3. Commit the data change and the regenerated manifest in the same PR so the
   digest change is visible in review. The robot runtime never runs this
   script.

`.gitattributes` marks `core/ethics_core/**` as `-text` so line-ending
conversion cannot change the pinned bytes on checkout.

### Limits (by design, stated plainly)

The digest is pinned in code, not signed. This stops on-disk tampering of
the data files, including editing a file together with its self-declared
hash. It does not stop an attacker who can also rewrite the installed Python
code; that needs install/package integrity (signed release bundles with a
public key held by the runtime and the private key held offline), which is
planned follow-up work.

## Governor process isolation

Physical action proposals are decided by a separate OS process, not by code
in the caller's process.

- **Process boundary.** `integrations.openclaw.OpenClawBridge()` (no injected
  engine) holds only a `multiprocessing` pipe to the governor
  (`core/governor.py`, `spawn` start method). The governor builds its own
  `EthicsEngine` after verifying the ethics core itself (gap 1 path). The
  caller cannot reach the governor's engine, ontology or decision state.
- **Strict protocol.** JSON, protocol version 1, 64 KiB cap per message.
  The request is an exact allow-list (`v`, `id`, `op`, `kind`, `text`,
  `user_id`, `context`), and `context` may only carry `user_id`,
  `embodied_action`, `platform_signals` and `source`. Rules, ontology data,
  paths, manifests and flags are refused (`protocol_violation`, deny). The
  governor entry point takes nothing but its pipe end.
- **Fail closed.** Governor not running, starting, crashed, killed
  mid-request, timed out, or a reply that is malformed, oversized,
  unversioned, the wrong version, for a different request id, or has extra
  keys: the client raises and `authorize()` denies and audits it. A tampered
  core in the governor process means it never reports ready, so everything
  is denied. Time budgets are unchanged: 0.25 s physical, 10 s speech.
- **Restart policy.** After a crash or timeout the client kills the governor
  and respawns it without blocking; requests made while it restarts are
  denied, never allowed. At most 3 restarts per 60 s, after which it stays
  down (deny everything) until PBE is restarted.
- **Speech choke point.** `api.InteractionSession` turns and
  `ResponseGenerator.generate_from_evaluate` call the gate through
  `authorize()` (core integrity check, speech budget, audit). A test scans
  the action and speech entry modules to prove every `evaluate()` call there
  is wrapped by `authorize()`.

### Limits (by design, stated plainly)

- **Speech is audited, not yet isolated.** Speech evaluation still runs in
  the caller's process because it depends on live per-user bond, memory and
  baseline objects. Moving it behind the boundary needs a per-user state
  store owned by the governor; that is follow-up work.
- **In-process test seam.** `OpenClawBridge(ethics_engine=...)` still
  accepts an injected engine for tests. It is not reachable from any
  environment variable, config key or flag, is still routed through
  `authorize()`, and is audited as `gate_mode=in_process_injected`. Code
  that can construct the bridge already runs in the caller's process; the
  real fix is that actuators should require proof of a governor decision
  (signed, expiring action tokens), which is follow-up work.
- Same as gap 1, this does not stop an attacker who can rewrite the
  installed Python code (signed install bundles are follow-up work).
