# Tests

Integration and smoke tests for the Positronic Bond Engine. These are standalone scripts (not a full pytest suite).

This folder holds:

- **Newer module tests** — local persistence, per-user baseline memory, exploratory questioning
- **Earlier deliberation / harm-prevention tests** — structured deliberation (v2), dual RH + User Agency deliberation, limited-data notes, and harm-prevention boundary override

## How to run

From the **project root** (so local packages like `core` and `persistence` resolve correctly):

```bash
# PowerShell — if imports fail without it:
$env:PYTHONPATH = "."

# Newer module tests
python tests/test_persistence.py
python tests/test_per_user_baseline.py
python tests/test_exploratory_questioning.py

# Earlier deliberation / harm-prevention tests
python tests/test_deliberation_v2.py
python tests/test_dual_deliberation.py
python tests/test_limited_data.py
python tests/test_harm_prevention.py
```

Or as modules:

```bash
python -m tests.test_persistence
python -m tests.test_limited_data
# …same pattern for the others
```

Persistence-related scripts use a temporary data folder and clean up after themselves. They do not write into the real `pbe_data/` directory when run as designed.
