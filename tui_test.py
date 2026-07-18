# SPDX-License-Identifier: Apache-2.0
"""
Proves the Tier-0 cockpit (menu TUI) over a real repo: it renders and quits, and its land flow is
GATED — an empty or mistyped confirmation lands NOTHING (the guard standing over canon), while the
exact proposal id confirms and lands. The menu drives the same admin.run() the CLI does, so this
locks the one behavior unique to the menu: the confirm step that protects the stamp.
"""
import builtins
import os
import subprocess as sp
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stasima.local_capstore import LocalCapStore, Identity
from stasima.entries import compose_entry
from stasima.canon import canon_seq, seq_display
from stasima import tui

entry = lambda title, body: compose_entry({"type": "kno", "title": title, "status": "active"}, body).encode()

work = tempfile.mkdtemp(prefix="cap-tui-")
gd = os.path.join(work, "stasima.git")
sp.run(["git", "init", "--bare", "-q", gd], check=True)
store = LocalCapStore(gd, approvers={"practitioner"})
store.bootstrap_canon({"practice/seed.md": entry("Seed", "the seed")}, "bootstrap")

# one additive proposal with its required log entry (seq 3c = origin 3b + 1), built straight in git
store.create_branch("refs/cap/proposals/p-1", store.resolve_ref("refs/heads/main"))
log = compose_entry({"type": "log", "title": "::3C", "status": "active", "seq": "3c"},
                    "::3C — first land.").encode()
store.commit("refs/cap/proposals/p-1",
             {"practice/principle.md": entry("Principle", "a principle"), "meta/log/3c.md": log},
             "propose", Identity("research-2"),
             expected_parent=store.resolve_ref("refs/cap/proposals/p-1"), op_id="op-2")

cfgpath = os.path.join(work, "stasima.toml")
with open(cfgpath, "w", encoding="utf-8") as f:
    f.write(f'git_dir = "{gd.replace(os.sep, "/")}"\n')

canon = lambda: store.resolve_ref("refs/heads/main")


def drive(*lines):
    """Run the menu with a scripted input sequence; when it's exhausted, EOF quits the loop cleanly."""
    it = iter(lines)
    def feed(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError      # _prompt treats EOF as 'quit'
    builtins.input = feed
    return tui.main(["--config", cfgpath])


base = canon()

# renders and quits, touching nothing
assert drive("q") == 0
assert canon() == base, "quitting changes nothing"

# Proposals -> pick #1 -> EMPTY confirm: the gate holds, nothing lands
assert drive("2", "1", "") == 0
assert canon() == base, "an empty confirmation must not land — the guard over canon"

# a MISTYPED confirm also cancels
drive("2", "1", "p-1-wrong")
assert canon() == base, "a mistyped confirmation must not land"

# the EXACT proposal id confirms the stamp -> it lands, canon advances to ::3C
drive("2", "1", "p-1")
assert canon() != base, "the proposal id confirms the stamp"
assert "practice/principle.md" in store.list_paths("refs/heads/main"), "the proposal landed in canon"
assert seq_display(canon_seq(store)) == "::3C", "state number advanced on the menu land"

# Bindings screen: renders empty; then the clear (rekey) gate holds — the same discipline as the
# land gate: empty and mistyped confirmations clear NOTHING, the exact port token re-arms learning
from stasima.cap_server import components_from_config, port_bindings
from stasima.config import Config
assert drive("4") == 0                                       # empty sticky table renders, EOF quits
_, _, _, audit, _, _ = components_from_config(Config.load(cfgpath))
audit.append("Recto", "port_binding", detail={"port": "port-a", "action": "learn", "mode": "strict"})
drive("4", "c1", "")
assert port_bindings(audit)["port-a"]["instance"] == "Recto", "an empty confirmation must not clear"
drive("4", "c1", "port-wrong")
assert port_bindings(audit)["port-a"]["instance"] == "Recto", "a mistyped confirmation must not clear"
drive("4", "c1", "port-a")
assert port_bindings(audit)["port-a"]["instance"] is None, "the exact port token clears — learning re-armed"

# HTTP-service screen: declines creation cleanly; creates the separate toml on 'y' (default port);
# status renders DOWN; start/stop not exercised here (no real service in the suite)
assert drive("7", "") == 0
assert not os.path.exists(cfgpath.replace(".toml", "-http.toml")), "declining must create nothing"
drive("7", "y", "", "")
httpcfg = cfgpath.replace(".toml", "-http.toml")
assert os.path.exists(httpcfg), "y must write the http toml"
text = open(httpcfg, encoding="utf-8").read()
assert 'transport = "http"' in text and "http_port = 8787" in text, text

print("OK -- cockpit: renders + quits; land gate holds (empty/mistyped cancel, exact id lands ::3C); "
      "bindings screen renders + clear gate holds (exact token rekeys); http screen creates the "
      "separate toml on request and never on decline.")
