# PBE Platform Integration Assumptions (Assumptions-of-Use Checklist)

**Status:** documentation only. This is Phase 5 Tier E scaffolding item 5
of 5 — see `docs/platform_safety_architecture.md` §4.5 for the design
rationale and §1's summary of the ISO 26262 SEooC (Safety Element out of
Context) pattern this checklist follows: rather than claim PBE is
safety-rated in the abstract, publish exactly what a platform integrator
must supply for PBE's gate outputs to mean anything safety-relevant for
that platform.

**No real integration exists yet.** Nothing here has been checked against
real hardware — Tier E itself (the real embodiment adapter) has not
started; this checklist is prep work for whenever it does. Every item
below is written as a literal checklist an integrator could tick through
at that point, not prose to interpret.

**Scope, restated from `docs/platform_safety_architecture.md` §2 because
it's the load-bearing fact underneath every item below:** PBE is a
deliberation/decision layer — approve, approve-with-conditions, hold,
refuse, identity-required. It is **not**, and does not claim to be, a
SIL-rated or ASIL-rated safety function, and it is **not** a substitute
for a platform's own protective-stop, Speed & Separation Monitoring,
Power & Force Limiting, or e-stop implementation. Per `architect ops notes (private)` §4, no
public or investor-facing material may describe PBE as "certified,"
"SIL-rated," "meets ISO 26262/13482," or similar unless a real, documented
safety case and third-party assessment exists. None does today, and
nothing in this checklist changes that.

---

## Before wiring PBE's gate output into anything safety-relevant, the platform must supply:

### A. An independently-rated protective-stop capability

- [ ] A protective-stop (or equivalent e-stop / safety-rated monitored
      stop) mechanism exists on the platform, rated and verified
      independently of PBE.
- [ ] It functions correctly with PBE offline, unreachable, hung, or
      returning garbage — i.e. it does not read, wait on, or depend on
      any PBE output to activate.
- [ ] It has been tested with PBE's process killed mid-decision, not just
      with PBE never started.

*(ISO 13482:2014's protective-stop requirement; docs/platform_safety_architecture.md §1/§4.3/§4.4.)*

### B. A declared, machine-readable safety envelope

- [ ] The platform publishes a concrete safety envelope PBE can read:
      max speed near a person, max force, minimum separation distance,
      end-effector hazard class, at minimum.
- [ ] The envelope is enforced **on the platform side**, independently of
      PBE. PBE's `speed_cap` / `require_clearance` conditions
      (`integrations/openclaw.py::_map_stance_to_gate`) are read as
      *tightening within* this envelope, never as *defining* it.
- [ ] Nobody on the integration team is treating PBE's conditions as a
      substitute for this envelope existing. (Worth stating explicitly —
      it's the easiest assumption to accidentally invert.)

*(docs/platform_safety_architecture.md §4.2. No envelope object exists in PBE yet — this remains a real gap, not just a documentation formality, until a platform actually supplies one.)*

### C. Trustworthy proximity / presence signals

- [ ] `near_person`, `unknown_persons`, and distance-style signals fed
      into `ActionProposal.payload` / `platform_signals` are accurate at
      the fidelity PBE's existing conditions already assume.
- [ ] The platform has verified its own sensor fidelity for these
      signals. **PBE has no way to verify this itself and currently
      trusts these signals at face value** — this is not a hedge, it's a
      literal description of what the code does today.
- [ ] The `degraded_sensor` platform state
      (`integrations/platform_states.py::PlatformState.DEGRADED_SENSOR`)
      is set whenever sensor confidence drops, so PBE-side callers that
      choose to read it can widen their own caution accordingly.

*(docs/platform_safety_architecture.md §4.4's "ambiguous / partial failure" case.)*

### D. A watchdog / heartbeat consumer, owned by the platform

- [ ] The platform runs its own watchdog process, independent of PBE's
      main reasoning loop, that polls PBE's liveness.
- [ ] `integrations/liveness.py::LivenessMonitor` (or an equivalent a real
      adapter builds against) is wired so PBE's own code calls `.beat()`
      around its decision loop (e.g. around `EthicsEngine.evaluate()` /
      `OpenClawBridge.submit_action_proposal()`) — **not done
      automatically today; a real integration must call this itself.**
- [ ] The platform's watchdog treats a stale heartbeat (`is_stale()` ==
      `True`, or `status().pbe_state ==
      PBEState.UNAVAILABLE_FAILED_CLOSED`) **identically to a REFUSE** —
      forcing its own `protective_stop_active` state — never as a silent
      pass-through, and never by waiting for PBE to confirm anything
      further.
- [ ] This has been tested by actually killing or hanging the PBE process
      and confirming the platform stops on its own, not just by reading
      the code and agreeing it should.

*(docs/platform_safety_architecture.md §4.4/§4.7 — the ROS-Safety Working Group watchdog pattern.)*

### E. A confirmed latency budget for that platform's real cadence

- [ ] The platform's actual sensor/actuation cadence has been measured —
      not assumed — and compared against PBE's own measured latency.
- [ ] Nothing safety-critical on the platform waits on PBE's decision
      loop to complete. PBE's reference numbers
      (`core/latency_budget.py::CONTEXTUAL_JUDGE_WARM_REFERENCE_SECONDS`
      / `CONTEXTUAL_JUDGE_COLD_REFERENCE_SECONDS`, ~0.9s / ~3.4s against a
      real local model) are several orders of magnitude too slow for any
      reflex-speed floor — this is treated as a hard architectural fact
      by the integration, not a target to optimize away.
- [ ] If the integration ever measures a PBE-backed decision responding
      fast enough to look reflex-capable (under
      `core/latency_budget.py::REFLEX_SPEED_CEILING_SECONDS`), that is
      investigated as a likely sign something didn't actually deliberate
      — not treated as a welcome speedup. (`assert_not_reflex_capable()`
      exists for exactly this check.)

*(docs/platform_safety_architecture.md §4.6.)*

### F. The hardware handshake is real, not a formality

- [ ] Every PBE approval is treated as a **proposal**, never a command.
- [ ] A concrete `PlatformValidator`
      (`integrations/openclaw.py::PlatformValidator`) is implemented
      against live sensor state / the declared safety envelope (item B)
      and passed to `OpenClawBridge(platform_validator=...)`, so an
      already-gate-approved proposal gets one more real check —
      re-validated against *current* state, not the state at the moment
      PBE decided — before it actually executes.
- [ ] Platform-side rejections are monitored over time (they land in
      `ActionGateResult.execution_log`, prefixed
      `platform_handshake_rejected:`) rather than only checked reactively
      after an incident — a pattern of rejections is itself a signal
      worth investigating.

*(docs/platform_safety_architecture.md §4.3.)*

### G. States are declared, not assumed

- [ ] The platform sets `ActionProposal.platform_state`
      (`integrations/platform_states.py::PlatformState`) honestly on
      every proposal it submits — including `protective_stop_active`,
      `estop_engaged`, `maintenance_mode`, `degraded_sensor`, and
      `manual_override_active` (ISO 10218 Hand Guiding) when applicable,
      not just the default `operational`.
- [ ] The platform reads `ActionGateResult.pbe_state`
      (`integrations/platform_states.py::PBEState`) and treats
      `unavailable_failed_closed` identically to a REFUSE, per item D.

---

## What PBE provides today to build against

Concrete, tested code an integrator can build a real adapter on top of —
none of it wired into `EthicsEngine.evaluate()`'s live decision pipeline,
all of it additive scaffolding built 2026-08-15 per
`docs/platform_safety_architecture.md`'s gap list:

| Assumption above | PBE-side artifact | Status |
|---|---|---|
| G (states) | `integrations/platform_states.py` (`PlatformState`, `PBEState`) | Scaffolded, additive fields on `ActionProposal`/`ActionGateResult` |
| F (handshake) | `integrations/openclaw.py` (`PlatformValidator`, `ValidatorDecision`) | Scaffolded, optional second stage in `OpenClawBridge` |
| D (heartbeat) | `integrations/liveness.py` (`LivenessMonitor`) | Scaffolded, pure interface — platform-side enforcement is NOT built here |
| E (latency) | `core/latency_budget.py` (`measure_latency`, `assert_not_reflex_capable`) | Scaffolded, reference constants + a callable canary |
| A, B, C | — | Not started. These are platform-owned by design (docs/platform_safety_architecture.md §3) — PBE was never going to build them, only read what the platform declares. |

None of A-C are PBE's to build — per the layered architecture in
`docs/platform_safety_architecture.md` §3, the bottom (reflex) and
mid (health-monitoring) layers are platform-owned, and PBE sits at the
top by design. Listing them here is about what the platform integration
must supply, not a PBE roadmap item.
