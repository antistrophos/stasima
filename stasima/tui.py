# SPDX-License-Identifier: Apache-2.0
"""
Stasima Cockpit (Tier-0, beta) — a menu front-end over the admin cockpit, so the practitioner can land
requests and run maintenance without keeping commands (or `--config`) handy. Pure stdlib.

It drives the SAME `run(args)` the CLI does — by synthesizing the exact argparse namespace — so there
is no second code path to keep in sync: the menu is just a different door into one cockpit. Whatever
the CLI refuses (a conflict, an append-only removal, a bad log entry), the menu refuses identically,
because it is literally the same call.

    python -m stasima.tui --config stasima.toml        # or set STASIMA_CONFIG and omit --config

Landing here is the CONSOLE channel: you are sitting at the terminal, so your presence IS the gate —
no TOTP (that is the airlock, for approving *through* an instance over a relay). The confirm step is
deliberateness, not cryptography. The instance does not run this; the practitioner does.
"""
import argparse
import os
import sys

from .admin import run, build_parser
from .config import Config


# ---------------------------------------------------------------- color (graceful degrade)
def _enable_vt() -> bool:
    """Turn on ANSI on Windows consoles; harmless elsewhere. False if it can't be armed."""
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)                       # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if not k.GetConsoleMode(h, ctypes.byref(mode)):
                return False
            k.SetConsoleMode(h, mode.value | 0x0004)      # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            return False
    return True


_COLOR = _enable_vt() and sys.stdout.isatty()


def _c(code, s):
    return f"\033[{code}m{s}\033[0m" if _COLOR else str(s)


BOLD = lambda s: _c("1", s)
DIM = lambda s: _c("2", s)
RED = lambda s: _c("31", s)
GREEN = lambda s: _c("32", s)
YELLOW = lambda s: _c("33", s)
CYAN = lambda s: _c("36", s)


def _rule():
    return DIM("─" * 72)


# ---------------------------------------------------------------- the one bridge to the cockpit
def _call(config, cmd, *extra):
    """Run a cockpit command through the CLI's own run(). Returns (result_dict, error_str) — exactly
    one is non-None. SystemExit is how run() reports a refusal (conflict, append-only, bad approver),
    so we catch it and surface the message instead of letting it tear down the menu."""
    argv = ["--config", config, cmd, *extra]
    try:
        return run(build_parser().parse_args(argv)), None
    except SystemExit as e:                    # run()'s refusal channel — message is the payload
        return None, str(e.code if e.code is not None else e)
    except Exception as e:                     # anything unexpected stays inside the loop
        return None, f"{type(e).__name__}: {e}"


def _prompt(s):
    """input() that treats Ctrl-C / Ctrl-Z / EOF as 'quit' rather than a crash."""
    try:
        return input(s).strip()
    except (EOFError, KeyboardInterrupt):
        return "\x00"                          # sentinel: quit


# ---------------------------------------------------------------- views
def _header(config, name):
    st, err = _call(config, "status")
    if err:
        return f"{BOLD('Stasima Cockpit')} {DIM('(beta)')} · {name}   {RED('status error — ' + err)}"
    healthy = st["audit_verify_ok"] and st["audit_vs_anchor"]
    audit = GREEN("audit ✓") if healthy else RED("audit ✗")
    unread = f"   {YELLOW('unread ' + str(st['practitioner_unread']))}" if st["practitioner_unread"] else ""
    return (f"{BOLD('Stasima Cockpit')} {DIM('(beta)')} · {CYAN(name)}    "
            f"canon {BOLD(st['canon_seq'])} ({st['canon_head'][:7]})    "
            f"{audit}    proposals {len(st['proposals'])}{unread}")


def _show_status(config):
    d, err = _call(config, "status")
    if err:
        print(RED("! " + err)); return
    print(BOLD("\nCanon"))
    print(f"  head    {d['canon_head'][:12]}")
    print(f"  seq     {d['canon_seq']}")
    print(BOLD("Health"))
    print(f"  audit chain   {GREEN('ok') if d['audit_verify_ok'] else RED('FAILED')}"
          f"   ({d['audit_events']} events)")
    print(f"  vs anchor     {GREEN('ok') if d['audit_vs_anchor'] else RED('MISMATCH')}")
    print(BOLD("Instances"))
    print("  " + (", ".join(d["perspectives"]) or DIM("none")))
    print(BOLD(f"Proposals ({len(d['proposals'])})"))
    for p in d["proposals"]:
        print(f"  {p}")
    if d["staged"]:
        print(BOLD("Staged (airlock)"))
        for s in d["staged"]:
            print(f"  {s['proposal_id']}  → {s['staged_oid'][:8]}")


def _print_preview(pid, pv):
    print(BOLD(f"\n{pid}"))
    for a in pv["adds"]:
        print(GREEN(f"  + {a}"))
    for m in pv["modifies"]:
        print(YELLOW(f"  ~ {m}"))
    for r in pv["removes"]:
        print(RED(f"  - {r}"))
    if not (pv["adds"] or pv["modifies"] or pv["removes"]):
        print(DIM("  (no changes — already in canon, or empty)"))
    log = GREEN("✓ one") if pv["log_entry_ok"] else RED(f"✗ {len(pv['log_entries'])}")
    removes = RED(f"{len(pv['removes'])} — append-only, land will refuse") if pv["removes"] else GREEN("none")
    print(f"  removes: {removes}    log entry: {log}    → would land at ::{pv['expected_seq'].upper()}")
    if pv["conflicts"]:
        print(RED(f"  conflicts: {pv['conflicts']}"))
    if pv.get("authors"):
        print(DIM(f"  authors: {', '.join(pv['authors'])}"))


def _proposals(config):
    st, err = _call(config, "status")
    if err:
        print(RED("! " + err)); return
    props = st["proposals"]
    staged = {s["proposal_id"] for s in st.get("staged", [])}
    if not props:
        print(DIM("\nno open proposals.")); return
    print(BOLD("\nProposals:"))
    for i, p in enumerate(props, 1):
        flag = YELLOW("  (staged)") if p in staged else ""
        print(f"  {i:>2}  {p}{flag}")
    pick = _prompt("\nNumber to preview/land, or Enter to go back: ")
    if pick in ("", "\x00"):
        return
    pid = None
    if pick.isdigit() and 1 <= int(pick) <= len(props):
        pid = props[int(pick) - 1]
    elif pick in props:                         # typing the id directly also works
        pid = pick
    if pid is None:
        print(RED("not a valid choice.")); return

    pv, err = _call(config, "preview", pid)
    if err:
        print(RED("! " + err)); return
    _print_preview(pid, pv)

    # gate the offer on the same conditions land enforces, so we never tee up a doomed stamp
    if not (pv["adds"] or pv["modifies"] or pv["removes"]):
        print(DIM("\nnothing to land here.")); return
    if pv["would_remove_canon"]:
        print(RED("\nThis would REMOVE canon paths. Canon is append-only — land will refuse. "
                  "Re-author (supersede, don't delete) before landing.")); return
    if not pv["log_entry_ok"]:
        print(YELLOW("\nNot landable yet: a proposal needs exactly one meta/log/<seq> entry. "
                     "Land will refuse until it does.")); return

    # console channel: presence (you, here) + a deliberate confirmation. Not a y/N — typing the id
    # is the fat-finger guard appropriate to stamping canon.
    print(BOLD(f"\nLand {CYAN(pid)} → canon ::{pv['expected_seq'].upper()}"))
    conf = _prompt("Type the proposal id to confirm the stamp (Enter cancels): ")
    if conf != pid:
        print(DIM("cancelled — nothing landed.")); return
    res, err = _call(config, "land", pid)
    if err:
        print(RED("✗ not landed — " + err)); return
    print(GREEN(f"\n✓ landed → {res['display']}   ({res['landed'][:8]})   "
                f"anchored {str(res.get('anchor', ''))[:8]}"))


def _inbox(config):
    d, err = _call(config, "inbox")
    if err:
        print(RED("! " + err)); return
    msgs = d.get("unread", [])
    if not msgs:
        print(DIM("\ninbox clear — no unread mail.")); return
    print(BOLD(f"\nUnread ({len(msgs)}):"))
    for i, m in enumerate(msgs, 1):
        print(f"  {i:>2}  {CYAN(m['from'])}  {m['subject']}")
        print(DIM(f"       {m['path']}"))
    pick = _prompt("\nNumber to mark read, or Enter to go back: ")
    if pick.isdigit() and 1 <= int(pick) <= len(msgs):
        path = msgs[int(pick) - 1]["path"]
        _, err = _call(config, "inbox", "--read", path)
        print(RED("! " + err) if err else GREEN(f"marked read: {path}"))


def _maintenance(config):
    actions = {"1": ("reindex", "rebuild the MAP search index from git"),
               "2": ("reconcile", "backfill audit events for any committed op missing one"),
               "3": ("verify", "re-check the audit chain + the git-anchored checkpoint"),
               "4": ("anchor", "write the current audit head into git now")}
    print(BOLD("\nMaintenance"))
    for k, (cmd, desc) in actions.items():
        print(f"  {BOLD(k)}  {cmd:<10}{DIM('— ' + desc)}")
    pick = _prompt("> ")
    if pick not in actions:
        return
    cmd = actions[pick][0]
    print(DIM(f"running {cmd}…"))
    res, err = _call(config, cmd)
    print(RED("! " + err) if err else GREEN("done: ") + str(res))


def _backup(config):
    print(BOLD("\nBackup"))
    print(f"  {BOLD('1')}  local backup   {DIM('— folder; carries the TOTP secret (same-trust move)')}")
    print(f"  {BOLD('2')}  remote mirror  {DIM('— git URL; content + audit, secret NEVER pushed')}")
    pick = _prompt("> ")
    if pick == "1":
        dest = _prompt("destination folder: ")
        if dest and dest != "\x00":
            res, err = _call(config, "backup", dest)
            print(RED("! " + err) if err else GREEN("backed up: ") + str(res))
    elif pick == "2":
        url = _prompt("git remote URL: ")
        if url and url != "\x00":
            res, err = _call(config, "mirror", url)
            print(RED("! " + err) if err else GREEN("mirrored: ") + str(res))


# ---------------------------------------------------------------- loop
def main(argv=None) -> int:
    try:   # Windows consoles default to cp1252, which can't print the box chars / em dashes / ✓
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="stasima-cockpit",
                                 description="Stasima practitioner cockpit (menu) — beta")
    ap.add_argument("--config", default=os.environ.get("STASIMA_CONFIG"),
                    help="path to the deployment's stasima.toml (or set STASIMA_CONFIG)")
    args = ap.parse_args(argv)
    if not args.config:
        print(RED("no config — pass --config <stasima.toml> or set STASIMA_CONFIG")); return 2
    try:
        name = Config.load(args.config).deployment_name or "cockpit"
    except Exception as e:
        print(RED(f"could not load config {args.config!r}: {e}")); return 2

    menu = (f"  {BOLD('1')}  Status        {DIM('— full dashboard')}\n"
            f"  {BOLD('2')}  Proposals     {DIM('— preview & land   ← the gate')}\n"
            f"  {BOLD('3')}  Inbox         {DIM('— practitioner mail')}\n"
            f"  {BOLD('4')}  Maintenance   {DIM('— reindex / reconcile / verify / anchor')}\n"
            f"  {BOLD('5')}  Backup        {DIM('— local backup / remote mirror')}\n"
            f"  {BOLD('q')}  Quit")
    dispatch = {"1": _show_status, "2": _proposals, "3": _inbox, "4": _maintenance, "5": _backup}

    while True:
        print("\n" + _rule())
        print(_header(args.config, name))
        print(_rule())
        print(menu)
        choice = _prompt("> ").lower()
        if choice in ("q", "quit", "\x00"):
            print(DIM("\nleaving the cockpit. canon stands where you left it."))
            return 0
        fn = dispatch.get(choice)
        if fn:
            fn(args.config)
        elif choice:
            print(DIM("pick 1–5 or q."))


if __name__ == "__main__":
    sys.exit(main())
