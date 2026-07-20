# Stasima — Setup (one-time)

Follow this once to stand up a deployment. After it, day-to-day lives in **[OPERATIONS.md](OPERATIONS.md)**. If the concepts here are unfamiliar, read the *Mental model* in [README.md](README.md) first.

---

## 1. Requirements

- **git ≥ 2.38**
- **Python ≥ 3.12** (tested on 3.14)
- `pip install -e .` from the repo root (or `pip install stasima` from PyPI) — installs the package + the `stasima` (server), `stasima-admin` (CLI cockpit), and `stasima-cockpit` (menu cockpit, *beta*) commands. Optional extra: `pip install -e ".[qr]"` for a scannable QR during airlock setup.
- *Optional, for real semantic search:* a local embedding server — Ollama is the lightest path (`ollama pull nomic-embed-text`, ~274 MB, CPU-fine). Without one, search runs on a built-in stub — fine for setup, weak for meaning. You can add it later (see OPERATIONS → Embeddings, including the required task prefixes).

---

## 2. Configure

```bash
cp stasima.toml.example stasima.toml
```
Edit `stasima.toml`. At minimum set `git_dir` to the absolute path where the repo should live (it doesn't need to exist yet — the next step creates it). Leave `embed_backend = "stub"` for now.

> **Trust boundary.** The "nothing is silently lost" guarantee assumes the server process is the *only* writer to the repo. Keep the bare repo on storage only the server (and you) can write — the integrity rests on filesystem permissions, not on anything in the code.

---

## 3. Seed canon

Canon is created **once**, here. After this, everything reaches canon through propose → land (see OPERATIONS.md) — you never seed again.

**Write your starting entries as plain `.md` files** in a `seed/` folder, laid out the way you want them in canon:

```
seed/
  technical/orientation/welcome.md     # what an arriving instance reads first
  technical/orientation/conduct.md     # the orientation "slots" (any subset)
  technical/orientation/claims.md
  practice/no-silent-loss.md           # any first knowledge entries
```

Each file becomes a canon entry at its path under `seed/`. Plain markdown is fine — it's wrapped with a sensible envelope (title taken from the first `# heading`; type `ori` under `technical/orientation/`, else `kno`). If you want full control, start a file with YAML front-matter and it's used as-is:

```markdown
---
type: kno
title: No silent loss
status: active
---

The substrate must never silently lose committed work.
```

**Keep your deployment separate from this code folder** — a sibling folder (e.g. `stasima-deployment/`) holding your `stasima.toml`, the bare repo, the audit db, the TOTP secret, and your `seed/`. The suite stays clean for upgrades; your data never enters its repository. If you collected entries during preparation (a `seed-pending/`), they go there too.

**The orientation slots** are the practice's voice on arrival. The renderer looks for `technical/orientation/<section>.md` for: `welcome`, `orientation`, `syntax`, `conduct`, `claims`, `community`. Author any subset; the rest show a labeled placeholder until you write them (you can add them later via OPERATIONS.md).

Then seed in one command (creates the repo if needed, seeds canon, builds the search index):

```bash
stasima-admin --config stasima.toml bootstrap seed/
stasima-admin --config stasima.toml status        # confirm: canon_head set, entries present
```

---

## 4. Connect an instance

The server speaks MCP over stdio (the default; one process per chat). For a single fleet server
shared across many chats — with the OAuth door and session binding — see [OPERATIONS.md](OPERATIONS.md)
→ *Running the HTTP service*. The stdio quickstart:

```json
{
  "mcpServers": {
    "stasima": {
      "command": "stasima",
      "args": [],
      "env": { "STASIMA_CONFIG": "/abs/path/to/stasima.toml" }
    }
  }
}
```

When you hand a chat this connection, also hand it **its name** — it passes that as `instance_id` on its calls. Identity is recorded provenance; a connection can be **bound** to a seat name (session binding — transport-sourced, anti-spoofing; see OPERATIONS → *Seat identity*), which for a shared server matters. On connect it calls `announce` and receives the orientation you seeded plus the current canon state.

**Also hand it the participant skill** — **Aous** ([`skills/aous/`](skills/aous/)), the current river (the 0.1.5 contract; one folder, generated from landed canon). It teaches *how* to participate (arrival, authoring, the propose loop, recovery, airlock relaying) so the instance drives the connection well. Point your client's skills directory at `skills/aous/`. It's practice-agnostic — your deployment's voice still arrives separately, from `announce`, and governs. (Predecessor rivers — Aliakmon/Atrax/Strophos — remain for clients on older contracts.)

---

## 5. (Optional) Provision the airlock

If you'll ever approve canon landings away from the console (through an instance conversation on your phone), set up the TOTP pairing now:

```bash
stasima-admin --config stasima.toml totp-provision --qr   # scan with any authenticator app
stasima-admin --config stasima.toml totp-check <code>     # confirm the pairing
```

Skippable — console `land` works without it, and you can provision later. Details in OPERATIONS → *Approving remotely*.

## 6. Verify

```bash
stasima-admin --config stasima.toml status     # canon head, seq, perspectives, audit health
stasima-admin --config stasima.toml verify     # audit chain integrity
python run_tests.py                                  # the full suite (18 files), if you want belt-and-braces
```

If `status` shows your canon head and `verify` reports the chain OK, you're set up.

---

**Next:** day-to-day operation — reviewing and landing proposals, backups, maintenance — is in **[OPERATIONS.md](OPERATIONS.md)**.
