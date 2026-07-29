# Public interaction entry (binding contract)

Installer-facing product surface (**v0.5.0-dev**, active development/testing, not stable): submit one logical turn → receive one logical result.

| Item | Location |
|------|----------|
| Package | `api/` |
| Session | `api.InteractionSession` |
| Types | `TurnRequest`, `TurnResult` |
| Helper | `api.submit_turn` |
| Demo | `examples/public_entry_demo.py` |
| Tests | `tests/test_public_entry.py` |

`examples/private_architect_chat.py` is a **test harness only**. Integrators use `api` directly.

## Core guarantees (invariants)

1. **Per-user isolation** — Bond, memory, baseline, working agreements, enjoyment signals are scoped to one real `user_id`. No synthetic group identities. No cross-user leakage.
2. **Ethical gate is authoritative** — The Engine decides whether speech or action is allowed. `forces_speech` and `forces_question` are always false. Callers must not override hold or refuse.
3. **Session presence is explicit and ephemeral** — Multi-user presence is declared by the caller (or platform signals). When more than one person is present and the speaker is not identified, the Engine requests identity rather than assuming or merging.
4. **Address name belongs to the user** — Used only to address that user; never claimed as the system’s identity.
5. **Development / testing honesty** — Active development/testing phase is visible; not presented as a finished stable product.
6. **No consciousness claims** — No claims of consciousness, qualia, or inner experience.
7. **Local-first data** — Default durable root is local and outside the install/source tree.
8. **Auditable decisions** — Decision, path, confidence, principles considered, and notes support later audit.

## Logical turn

**Input:** `user_id` (required for durable effects; may be provisional while establishing identity), `message`, optional `speaker_id`, optional presence updates, optional development context, optional platform signals.

**Output:** `decision`, `confidence`, `path`, `spoken_text` (only when the gate allows), force flags always false, self-audit / relationship-health notes, updated `presence`, resolved `user_id` (or null when identity-required). Never another user’s private data.

## Presence rules

- Session-scoped only; operations: `mark_present`, `mark_left`, `presence_current`, `clear_presence`.
- Multi-user + unidentified speaker → `IDENTITY_REQUIRED`, no bond/memory write.
- Explicit speaker routes durable effects to that user’s isolated stack only.

## Platform signals (seam only)

Optional keys (no vision stack, no raw media storage):

- Known people: `present_user_ids` / `company_user_ids`
- Unknown company: `unknown_persons` / `unknown_count` / `company_present`
- Suggested speaker: `suggested_speaker` (+ optional `speaker_confidence` 0–1)
- Other coarse activity/timing flags may be supplied; they do not invent identity

Low-confidence or unlisted suggested speakers are ignored. Ambiguity falls back to identity request.

## Non-goals

No chat UI · no shared group memory · no diagnostic claims · no engagement optimization · no consciousness/personhood claims · no required base model.

## Minimal usage

```python
from api import InteractionSession, TurnRequest

session = InteractionSession()  # default local data root
r = session.submit_turn(TurnRequest(message="hello", user_id="alice"))
assert r.forces_speech is False and r.forces_question is False

session.mark_present("bob")
r2 = session.submit_turn(TurnRequest(message="hello", user_id="alice"))
assert r2.decision == "IDENTITY_REQUIRED" and r2.user_id is None

r3 = session.submit_turn(TurnRequest(message="as bob: hello", user_id="alice"))
assert r3.user_id == "bob"
```
