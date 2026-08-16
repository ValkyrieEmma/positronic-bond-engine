# PBE Platform Safety & Standards Architecture

**Status:** design/documentation artifact. No production code shipped with this doc — the concrete code work it specifies is scoped as new Phase 5 sub-items in the roadmap, left for a Claude Code session with real shell/test access rather than done through the read-only-except-file-write device bridge this doc was written through.

**Origin:** this is the concrete artifact `internal design notes (private, not published)`'s Phase 5 / Tier E section already flagged as needed ("Architecture guidance ... proposed as the concrete artifact this guidance should turn into once Tier E work actually starts") and the specific research the outside reviewer the outside reviewer's 2026-08-04 review asked for ("study established standards ... the outside reviewer pointed to ROS, ISO, and IETF safety work specifically"). Written 2026-08-15, ahead of Tier E actually starting, at Emma's request.

**Scope note, stated up front so it can't get lost in the detail below:** none of this changes what PBE governs. PBE remains a deliberation/decision layer — approve, approve-with-conditions, hold, refuse, identity-required — never a hardware safety function. Every standard summarized here exists to protect people from a robot's *physical* failure modes (motion, force, collision), which is not what PBE does or claims to do. What this doc adds is standard vocabulary, testable structure, and an honest list of what a platform integrator must supply for PBE's decisions to mean anything once a real embodiment exists.

---

## 1. Standards referenced

| Standard | Domain | Core mechanism | Relevance to PBE |
|---|---|---|---|
| **IEC 61508** | Generic functional safety for electrical/electronic/programmable-electronic (E/E/PE) systems | Safety Integrity Levels (SIL 1–4), a defined safety lifecycle (hazard/risk analysis → requirements → design → verification → operation), independence and diagnostic-coverage requirements between safety and non-safety functions, fail-safe defaulting | The umbrella standard behind almost everything below. Its central discipline — a safety function must be independent of, and unable to be defeated by, a non-safety-rated component — is exactly the separation the roadmap already assumed (PBE ≠ the reflex layer) and is now the standard's own vocabulary, not just this project's own reasoning. |
| **ISO 26262** | Road-vehicle functional safety, derived from IEC 61508 | Automotive Safety Integrity Levels (ASIL A–D, +QM) from Severity × Exposure × Controllability; strict requirement-to-test traceability (V-model); "freedom from interference" between elements of different ASILs; the **SEooC** (Safety Element out of Context) pattern | Not directly applicable — PBE is not automotive — but its **SEooC concept is the right frame for how PBE should document itself for integrators**: a component built with explicit, stated assumptions about the system it will be embedded in, rather than a claim that it is safety-rated in the abstract. Section 5 below applies this pattern directly. |
| **ISO 13482:2014** | Safety requirements for personal-care robots (mobile servant robots, physical-assistant robots, person-carrier robots) | Robot-specific risk assessment; **protective stop** as a required capability, implemented independently of higher-level control; risk-reduction hierarchy (inherent safe design → protective measures → information for use) | The most directly applicable standard given PBE's actual target (a companion/assistant robot living with a person), more so than industrial-arm standards. Gives the roadmap's already-stated "reflex layer independent of PBE" a formal name — **protective stop** — and a testable requirement (stop within a bounded time/distance, verified independently of whatever software issued the last motion command). |
| **ISO 10218-1/2 + ISO/TS 15066** | Industrial and collaborative robot safety | Four collaborative operating modes: **Safety-rated Monitored Stop**, **Hand Guiding**, **Speed & Separation Monitoring (SSM)**, **Power & Force Limiting (PFL)** — each implemented at a safety-rated layer (Performance Level d / SIL 2 equivalent) independent of the controller issuing motion | Originated for industrial arms, but the vocabulary now shapes every robot-safety conversation, including personal-care robots. PBE's existing `speed_cap` / `require_clearance` conditions in `integrations/openclaw.py` are **advisory suggestions to the platform, not an implementation of SSM or PFL** — worth stating explicitly so nobody later mistakes an ethics-engine condition for a certified safety function. Also worth carrying forward: *"PFL does not make the end effector safe"* — force limiting the arm doesn't make a hot, sharp, or heavy end effector safe, and PBE has no visibility into end-effector hazard class today. |
| **ROS-Safety Working Group** (ros-safety/safety_working_group) | Community practice for building safety-conscious ROS/ROS 2 systems | A Safety Patterns Catalogue, a Safety-Critical ROS Cookbook, a **software watchdog library** (built on DDS QoS policies and ROS 2 lifecycle nodes), a C++ contracts library | No formal IEC 61508/ISO 26262 certification exists for stock ROS 2 core (some vendors, e.g. Apex.AI, have pursued certified distributions separately — this is an open item, not a claim to make). The **watchdog pattern** — a supervisor independent of the main reasoning loop that detects a hang and forces a safe state — is the concrete implementation of a principle PBE's roadmap already states in prose ("a hung PBE process must never remove the platform's baseline physical safety") and should be adopted by name. |
| **SEooC-for-ROS academic pattern** (Fernandes et al., *ISO26262 SEooC Compliance of a ROS Based Architecture*, WSEAS 2017) | Applying ISO 26262's SEooC pattern to a ROS-based component | Split processing into tiers by criticality; characterize timing/reliability behavior (message period, granularity, queue size) under stress testing; build the safety case around one specific, parameterized instantiation rather than an abstract claim | Directly analogous to work PBE has already half-done: `ContextualJudge`'s measured latency (~3.4s cold / ~0.9s warm, from the reasoning-over-rote design doc) is exactly the kind of characterization a SEooC safety case requires — it just hasn't been published as a stated assumption or backed by a repeatable benchmark yet. Section 4.5 below turns this into a concrete requirement. |

## 2. What PBE can and cannot claim

Stated explicitly because architect ops notes (private) already requires public framing to stay honest about current readiness, and safety claims are exactly the kind of claim that's easy to overstate by accident:

- PBE **is not, and does not claim to be**, a SIL-rated or ASIL-rated safety function. No formal safety case, hazard analysis, or third-party assessment has been performed against any of the standards above.
- PBE **is not** a substitute for a platform's own protective-stop, SSM, PFL, or e-stop implementation. Those must exist, be independently rated, and function whether or not PBE is running, reachable, or fast enough.
- What PBE **can honestly claim**: it reduces the likelihood that an unsafe or ethically-unsound command is *proposed* in the first place, and it refuses to *authorize* actions its deliberation flags — a supervisory/planning-layer contribution, not a reflex-layer guarantee. This matches the product's own 2026-08-04 marketing pivot decision ("can't be manipulated into harm," carefully scoped) — this doc gives that scoping a standards-grounded boundary rather than just an internal judgment call.
- Any future public or investor-facing material that uses words like "certified," "SIL-rated," "meets ISO 26262," or similar must not be used unless a real, documented safety case and assessment exists. Worth adding as a standing rule alongside architect ops notes (private)'s existing marketing constraints.

## 3. Layered architecture, restated in standards vocabulary

The roadmap's existing three-layer picture (from the outside reviewer's 2026-08-04 review) maps directly onto the standards' own layering, which is a good sign — nothing here required inventing new architecture, only naming what was already implicit:

```
Executive / high-level planning   <- PBE's deliberation gate lives here (openclaw.py, EthicsEngine)
Mid-level health monitoring        <- platform-owned; watches PBE's own liveness among other things
Low-level reflex / protective stop <- platform-owned, independently rated, must work with PBE absent
```

- IEC 61508's independence requirement, ISO 26262's "freedom from interference," and ISO 13482's protective-stop requirement all say the same thing from three different angles: **the bottom layer must not depend on the top layer's correctness or availability.** PBE sits at the top by design; nothing changes about where it sits, this just confirms the placement is the same one the standards would independently require.
- ISO 10218/15066's four collaborative modes live at the reflex/mid layer, not in PBE. PBE's job is to *know about* the platform's declared safety envelope (Section 4.2) and stay inside it when proposing conditions, not to implement SSM or PFL itself.

## 4. Architecture checklist (the artifact the roadmap already asked for)

Six items were already named in the roadmap (states/modes, safety envelope, hardware handshake, failure ownership, adapter-layer assumptions, latency targets/benchmarks), plus the minimum-necessary-intervention and outcome-branching items from the same section. Filled in here using the standards above; each ends with the concrete gap against the current codebase.

### 4.1 States and modes

The adapter contract needs an explicit, typed representation of both the platform's state and PBE's own state — today `integrations/openclaw.py` has neither.

Platform-side states (owned by the platform, PBE only reads them): `operational`, `protective_stop_active`, `estop_engaged`, `maintenance_mode`, `degraded_sensor`, `manual_override_active` (a person is physically hand-guiding the robot — ISO 10218's Hand Guiding mode).

PBE-side states (owned by PBE, the platform reads them): `available`, `deliberating`, `timeout`, `unavailable_failed_closed`. This last state matters most: **the platform must treat "PBE unavailable" identically to a REFUSE, never as a silent pass-through.**

**Gap:** `ActionProposal` / `ActionGateResult` in `openclaw.py` carry no state fields at all today. Nothing represents "the software is no longer in control," which the roadmap's own Tier E guidance already flagged as needed language, but no field exists to carry it. Scoped as a Phase 5 code task below, not done in this pass.

### 4.2 Safety envelope

A per-platform declared set of hard limits (max speed near a person, max force, minimum separation distance, end-effector hazard class) that PBE can read as a known constraint but never independently enforces — enforcement stays hardware-side, per Section 3. PBE's `speed_cap` / `require_clearance` conditions (already shipped in `openclaw.py`) should be read as *tightening within* the envelope when relationship or context signals warrant it, never as *defining* the envelope.

**Gap:** no envelope object exists yet; `openclaw.py`'s conditions are currently hardcoded string suggestions (`"speed_cap": "slow"`) rather than derived from a declared, platform-supplied envelope.

### 4.3 Hardware handshake

Every PBE approval is a **proposal**, not a command. The existing design doc language already says this; it needs to become an actual two-step handshake once real hardware exists:

1. PBE evaluates and returns approve / approve-with-conditions / hold / refuse.
2. The platform's own safety-rated layer independently re-validates the proposal against its current safety envelope and live sensor state before executing — and can reject even an approved proposal. The rejection reason should be fed back into PBE's audit trail so a pattern of platform-side rejections becomes visible over time, not silently dropped.

**Gap:** `OpenClawBridge._maybe_execute()` currently treats any non-vetoed `ActionGateResult` as final and executes it against the `SimulatedRobot` with no second validation step and no rejection-feedback path. Correct for a "toy but real" scaffold with no real hardware behind it yet; the two-step handshake needs to be built before this touches anything real.

### 4.4 Failure ownership

- **PBE fails** (crash, timeout, unreachable model endpoint): platform must default to protective stop / safe state. Never proceed on "no answer." This is already the stated principle (safety-hardening principle #5); this doc just ties it to the `unavailable_failed_closed` state above so it's implementable, not just statable.
- **Platform's safety layer fails**: squarely the platform's responsibility per ISO 13482/10218. PBE cannot compensate for it and no public material should imply otherwise (Section 2).
- **Ambiguous / partial failure** (e.g. sensor degraded but PBE still responding): the platform's `degraded_sensor` state (4.1) should cause PBE to widen its own caution — tighter conditions, more holds — consistent with the existing "unrecognized verdicts and exceptions block by default" posture already established in Phase 2's `get_next_candidate()` and generalized in Phase 2.5.

### 4.5 Adapter-layer assumptions (the SEooC contract)

Following the SEooC pattern in Section 1: rather than claim PBE is safety-rated, publish exactly what a platform integrator must supply for PBE's gate outputs to mean anything. Proposed as the actual **assumptions-of-use** list for the eventual Optimus (or any) adapter:

1. An independently-rated protective-stop capability that functions with PBE offline, unreachable, or hung (ISO 13482).
2. A declared, machine-readable safety envelope (Section 4.2) that PBE can read.
3. `near_person` / `unknown_persons` / distance signals trustworthy at the fidelity PBE's existing conditions already assume — PBE has no way to verify sensor fidelity itself and currently trusts these signals at face value.
4. A watchdog or heartbeat mechanism on PBE's own liveness (Section 4.6), owned by the platform.
5. A characterized latency budget for PBE's decision loop specific to that platform's sensor/actuation cadence (Section 4.7), confirmed before PBE's output is wired into anything time-sensitive.

**Gap:** none of this is written down anywhere as an explicit contract today — it lives across roadmap prose, this doc, and the outside reviewer's review notes. Worth its own short published doc once a real integration target exists (Optimus or otherwise), reusing this list as the seed.

### 4.6 Latency targets / benchmarks

PBE's decision loop is explicitly out of any reflex-speed path. Measured numbers already exist (`ContextualJudge`: ~3.4s cold / ~0.9s warm against a real local Ollama model, per the reasoning-over-rote design doc) — several orders of magnitude too slow for a millisecond-or-tighter reflex floor. PBE targets stay in the supervisory/planning cadence (seconds), consistent with the numbers already on record.

**Gap:** this constraint is documented in prose only. Nothing in the codebase asserts it — there's no guard that would fail loudly if a future change accidentally wired `ContextualJudge` or `EthicsEngine.evaluate()` into a decision path with a sub-second deadline. Worth a real benchmark/assertion, not just a comment, once Tier E work starts (Section 6).

### 4.7 Watchdog / heartbeat pattern

Borrowed directly from the ROS-Safety Working Group's own watchdog library pattern (DDS QoS + lifecycle-node based, Section 1): the platform — never PBE itself — should run a watchdog that detects a hung or unresponsive PBE process and forces the platform into `protective_stop_active` independent of PBE ever answering. This is the concrete implementation of failure ownership (4.4) and the `unavailable_failed_closed` state (4.1) — currently asserted only as a principle, not as a named pattern with a reference implementation to build against.

### 4.8 Minimum-necessary-intervention checklist

(Carried forward from the roadmap's own Phase 5 guidance, restated here as part of the same artifact rather than duplicated separately.) Prefer non-lethal and non-destructive options; prefer containment over destruction; escalate only when safer options are insufficient; use no more force or control than necessary; return autonomy to the person as soon as the emergency ends; review the intervention afterward. This is the embodied expression of Phase 1.5b's necessity/proportionality/reversibility work (`core/harm_dimensions.py`, `core/convergence_lock.py`) applied to actual physical force, speed, restraint, and proximity policy once hardware exists.

### 4.9 Outcome branching before high-impact physical action

Before a consequential embodied action, deliberation should consider at minimum: the intended outcome, a plausible failure outcome, and a plausible unintended or adversarial outcome. Benevolent intent alone is never sufficient justification. All three branches should be logged into `reasoning_trace` for embodied high-impact actions specifically — a natural extension of Phase 2.5's structured exception logging (the same discipline applied to two different failure modes: one prevents a single defeat from becoming precedent, this one prevents a single good intention from being treated as a complete safety analysis).

## 5. Gap list (summary)

Everything above ends in a gap note; collected here for quick reference. None of these are urgent — Tier E is still correctly sequenced behind Phases 2.5–4 per the roadmap, and none of this can be fully built or tested without real or simulated hardware to target. Listed so they aren't lost between now and when Tier E actually starts:

1. No states/modes representation anywhere in `integrations/openclaw.py` (4.1).
2. No safety-envelope object; conditions are hardcoded suggestions, not derived from a declared envelope (4.2).
3. No two-step hardware handshake or rejection-feedback path — PBE's approval is currently treated as final by the simulated executor (4.3).
4. No `unavailable_failed_closed` state to hang the failure-ownership principle on (4.4).
5. No published assumptions-of-use / SEooC contract for integrators (4.5).
6. No codified latency-budget assertion — the ~0.9s/~3.4s constraint lives in prose only (4.6).
7. No watchdog/heartbeat pattern named or scaffolded, despite the underlying principle already being stated (4.7).
8. No public-claims rule specifically about safety-standard language (certified/SIL-rated/etc.) — worth adding next to architect ops notes (private)'s existing marketing constraints (Section 2).

## 6. Where this goes next

This doc is documentation only, written through a read/write-capable but shell-less channel (no test suite, no git access from this session). The gap list above is exactly the input a real Claude Code session (with shell + pytest + git) needs to turn into actual code, once Tier E is picked up per the roadmap's existing sequencing — see the roadmap's Phase 5 section for the updated, dated pointers to this doc, and the accompanying Claude Code prompt for how to hand this off cleanly.

## References

- `internal design notes (private, not published)` — Phase 5 / Tier E section, safety-hardening principle #5.
- `internal design notes (private, not published)` — 2026-08-04 update, the outside reviewer the outside reviewer's review.
- `internal design notes (private, not published)` — Awake/Asleep state design (conceptually adjacent to, but distinct from, the platform `maintenance_mode` state in 4.1).
- IEC 61508, ISO 26262, ISO 13482:2014, ISO 10218-1/2, ISO/TS 15066 — public standard summaries (full citations in the accompanying research doc).
- ros-safety/safety_working_group (GitHub) — Safety Patterns Catalogue, Safety-Critical ROS Cookbook, watchdog library.
- Fernandes et al., *ISO26262 SEooC Compliance of a ROS Based Architecture*, WSEAS Transactions on Systems, 2017.
