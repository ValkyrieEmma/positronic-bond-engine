# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
PBE is pre-1.0 and experimental; 0.x releases may change behavior.

## [0.5.0] - Unreleased

First tagged release of the 0.5 line. Still experimental: not a production
robot stack, not certified, and not a hardware safety function.

### Security

- **Governor process isolation (security gap 2).** The deterministic governor
  (the `EthicsEngine` and the allow/deny decision) for physical action
  proposals now runs in its own OS process (`core/governor.py`). The caller
  holds only a pipe and talks a strict, versioned (v1), size-limited (64 KiB)
  JSON protocol whose request schema is an allow-list: no rules, ontology,
  paths, manifests or flags can be sent. The governor loads and verifies the
  ethics core itself. Not running, starting, crashed, timed out, malformed,
  oversized, unversioned or mismatched replies all deny, and are audited.
  Bounded restart policy (3 per 60 s, then stays down); requests made while
  restarting are denied.
- **Speech goes through `authorize()`.** `api.InteractionSession` turns and
  `ResponseGenerator.generate_from_evaluate` now run the gate through the
  authorization choke point with the 10 s speech budget, so speech is audited
  like physical actions. A gate failure becomes a HOLD and speech is withheld.
  A test scans the action and speech entry modules to prove every
  `evaluate()` call is wrapped by `authorize()`.
- **Verified, read-only ethics core (security gap 1, #7).** The ethics core
  directory is checked against sha256 digests pinned in code at load; any
  missing, extra, modified or unreadable file fails closed and
  `authorize()` denies every action with `failure="core_integrity"`. Loaded
  core data is immutable in memory, with no runtime override. Manifest is
  rebuilt only by a developer with `scripts/rebuild_ethics_manifest.py`.
- **Fail-closed action authorization (security gaps 4 + 5, #6).**
  `core/action_authorization.authorize()` is the single choke point between
  the gate and any side effect: gate exception, timeout, missing gate or any
  decision outside the explicit allow-list denies, with an audit entry.
  Physical proposals default to a 0.25 s gate budget, speech to 10 s.
- **Sanctity: model "benign" is non-final on life-stakes hits (#5).** A
  conclusive `ContextualJudge` benign verdict no longer demotes a Sanctity
  hit; the deterministic path decides, and only violation verdicts can
  tighten.

### Changed

- `OpenClawBridge()` with no injected engine uses the governor process. An
  injected `ethics_engine` remains as an in-process test seam (still routed
  through `authorize()`, audited as `gate_mode=in_process_injected`).
- `OpenClawBridge(development_context=...)` now raises `TypeError`; the
  governor owns its own configuration.
- Version `0.5.0.dev0` / `0.5.0-dev` becomes `0.5.0`.

[0.5.0]: https://github.com/ValkyrieEmma/positronic-bond-engine/releases/tag/v0.5.0
