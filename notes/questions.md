# FreightCheck — Open Questions & Assumptions Log

This file is where the coding agent records anything it could not resolve
from the specs alone. Humans resolve spec conflicts and ambiguities — the
agent's job is to surface them clearly, not to guess silently.

---

## How to use this file

Add a new entry whenever one of the following happens:

1. **Spec ambiguity** — two reasonable interpretations of a spec line, and
   you had to pick one to keep working.
2. **Spec conflict** — two specs appear to disagree in a way the priority
   rules (Data Models > others) don't cleanly resolve.
3. **Spec gap** — you needed information the specs didn't provide, and you
   made a minimal-blast-radius choice to keep moving.
4. **Possible spec error** — you believe a spec is wrong. Do NOT silently
   contradict it; record your concern and continue following the spec.
5. **Environment gap** — a required secret, account, or tool is missing.
6. **Deferred decision** — something is decided "for now" but should be
   revisited before a later milestone.

Do **not** use this file for:
- Progress notes ("finished M2 today")
- TODO lists for yourself (use the agent's own task tracking)
- Design musings ("wouldn't it be nice if...")

Keep it tight. One entry per issue. Resolved entries stay in the file so
the decision history is searchable.

---

## Entry template

Copy this block for each new entry. Entries are chronological (newest at
the bottom of the Open section).

```
### Q-<NNN>: <short title>

- **Raised**: <YYYY-MM-DD> during <milestone>
- **Type**: ambiguity | conflict | gap | possible-error | environment | deferred
- **Context**: <1–3 sentences on what you were trying to do>
- **Spec references**:
    - `freightcheck_<doc>.md` §<section>: <exact line or paraphrase>
    - `freightcheck_<doc>.md` §<section>: <exact line or paraphrase>
- **What I did**: <the choice you made and why it has the smallest blast
  radius>
- **What I need from a human**: <specific question or decision needed>
- **Blocking?**: yes | no — if yes, you should have stopped instead of
  choosing. Explain why you proceeded.
- **Status**: open | resolved
- **Resolution** (fill in when resolved): <answer> — decided by <who> on
  <YYYY-MM-DD>
```

---

## Open

<!-- New entries go here. Move to "Resolved" when a human answers. -->

---

## Resolved

<!-- Move entries here once they are answered. Keep them for history. -->
