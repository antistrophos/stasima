# SPDX-License-Identifier: Apache-2.0
"""
Canon lifecycle — the layer between storage and the protocol surface.

Owns: the state sequence (seq tags, ::N display), log-entry validation (every proposal lands with
its story attached), the practitioner's landing routine, and the index rebuild. Used by the server
(cap_server), the cockpit (admin), and the airlock — none of which should have to reach through the
protocol surface to get at lifecycle machinery.
"""
from .entries import parse_entry
from .local_capstore import LocalCapStore, PERSP_PREFIX, PROP_PREFIX, Identity, RefNotFound
from .map_index import index_entry
from .audit_log import anchor_audit_head

LOG_DIR = "meta/log/"
STATE_TAGS = "refs/tags/state/"
# Default sequence origin: this practice's chat-era freeze (::3B), kept as the suite default so the
# original deployment's continuity holds. A deployment sets `seq_origin` in config to start anywhere
# (0 -> first land is ::1). The first land is always origin + 1.
CHAT_ERA_FREEZE = 0x3B


def _instance_from_ref(ref: str):
    return ref[len(PERSP_PREFIX):] if ref.startswith(PERSP_PREFIX) else None


def _canon_positions(store: LocalCapStore, canon_tip) -> dict:
    """{path: position} — each path's position on CANON'S OWN clock: the first-parent spine index
    (oldest commit = 1) of the last canon commit that touched it. Canon entries are authored
    elsewhere (a proposal branch) and arrive through the gate, so their ENVELOPE pins describe the
    authoring coordinates — true, immutable, resolvable through the merge ancestry forever. The
    row's position on canon itself is this derived value; the two coordinate systems must never be
    conflated in one column (the pin-leak the 0.1.3 release review's critic caught)."""
    commits = store.rev_list(canon_tip)                       # first-parent spine, newest first
    total = len(commits)
    positions = {}
    for i, oid in enumerate(commits):
        pos = total - i                                       # oldest = 1, tip = total
        parent = commits[i + 1] if i + 1 < len(commits) else None
        touched = store.changed_paths(parent, oid) if parent else store.list_paths(oid)
        for p in touched:
            positions.setdefault(p, pos)                      # newest touch wins (walk is newest-first)
    return positions


def reindex_from_git(store: LocalCapStore, index, embedder, *, clear: bool = True) -> int:
    """Rebuild the MAP index from git — the derived-projection invariant, in code. Walks canon +
    every perspective, reads each entry, re-embeds, upserts. Also the canon-indexing-after-landing
    path and the model-swap / recovery path. Proposals are staging and are not indexed."""
    if clear:
        index.clear()
    canon = store.canon_ref
    canon_tip = store.resolve_ref(canon)
    refs = ([canon] if canon_tip else []) + [r.name for r in store.list_refs(PERSP_PREFIX)]
    canon_pos = _canon_positions(store, canon_tip) if canon_tip else {}
    n = 0
    for ref in refs:
        for path in store.list_paths(ref):
            if not path.endswith(".md"):
                continue
            envelope, body = parse_entry(store.read_blob(ref, path).decode("utf-8", "replace"))
            author = _instance_from_ref(ref)
            if author is None:                       # canon: the envelope's declared origin, else the
                # path's introducer. The introducer heuristic answers "who PROPOSED" wearing the label
                # "who authored" — a cross-proposed entry (carried toward canon by another seat, with
                # origin_author stamped by the propose guard) keeps its true author here.
                hist = store.history(ref, path)
                author = envelope.get("origin_author") or (hist[-1]["author"] if hist else "")
                # canon rows carry canon's own coordinates — the envelope keeps the authoring ones
                envelope = dict(envelope)
                envelope["instance_depth"] = canon_pos.get(path, 0)
            index_entry(index, embedder, ref=ref, path=path, is_canon=(ref == canon),
                        authoring_instance=author, content_oid=store.blob_oid(ref, path),
                        envelope=envelope, body=body)
            n += 1
    return n


# ---- log entries + the state sequence (the State Log's descendant) ----
def proposal_statuses(store) -> dict:
    """{proposal_id: lifecycle} — open | landed | closed(+closed_reason); open proposals carry
    `lands_behind`, the branch point's distance down canon's first-parent spine (the raw staleness
    fact — no threshold baked in: the window is a value for the practice to rule, not the code).
    An empty branch's tip sits ON the spine (open at its branch point); a landed proposal's tip is
    reachable but off-spine (it arrived as a merge's second parent) — that asymmetry is the test."""
    canon_tip = store.resolve_ref(store.canon_ref)
    spine_pos = {oid: i for i, oid in enumerate(store.rev_list(canon_tip))} if canon_tip else {}
    out = {}
    for r in store.list_refs(PROP_PREFIX):
        pid = r.name[len(PROP_PREFIX):]
        tip = store.resolve_ref(r.name)
        sub = store.tip_subject(r.name)
        if sub.startswith("close: "):
            out[pid] = {"status": "closed", "closed_reason": sub[len("close: "):]}
        elif tip in spine_pos:
            out[pid] = {"status": "open", "lands_behind": spine_pos[tip]}
        elif tip and canon_tip and store.is_ancestor(tip, canon_tip):
            out[pid] = {"status": "landed"}
        else:
            st = {"status": "open"}
            if tip and canon_tip:
                base = store.merge_base(canon_tip, tip)
                if base in spine_pos:
                    st["lands_behind"] = spine_pos[base]
            out[pid] = st
    return out


def close_proposal(store, audit, proposal_id: str, reason: str, actor: str, op_id: str = "") -> dict:
    """The terminal verb's shared body: a `close:` tombstone commit + the audit event. The caller
    enforces its own lane — the MCP tool checks creator-or-approver; the admin console IS the gate
    (clearing lingering offerings is its own duty). Idempotent: re-closing reports `already`."""
    ref = PROP_PREFIX + proposal_id
    tip = store.resolve_ref(ref)
    if tip is None:
        raise RefNotFound(ref)
    sub = store.tip_subject(ref)
    if sub.startswith("close: "):
        return {"proposal_id": proposal_id, "closed": True,
                "reason": sub[len("close: "):], "already": True}
    r = store.commit(ref, {}, f"close: {reason}", Identity(actor),
                     expected_parent=tip, op_id=op_id or f"close-{proposal_id}-{tip[:8]}")
    audit.append(actor, "propose_close", target_ref=ref, op_id=r.op_id, result_oid=r.oid,
                 detail={"reason": reason})
    return {"proposal_id": proposal_id, "closed": True, "reason": reason, "oid": r.oid}


def canon_seq(store, origin: int = CHAT_ERA_FREEZE) -> int:
    """Canon's current state number, read from the state/<seq> tags (hex). `origin` before any land."""
    vals = []
    for r in store.list_refs(STATE_TAGS):
        try:
            vals.append(int(r.name[len(STATE_TAGS):], 16))
        except ValueError:
            pass
    return max(vals, default=origin)


def seq_display(n: int) -> str:
    return f"::{format(n, 'X')}"


def validate_log_entry(store, prepared, origin: int = CHAT_ERA_FREEZE) -> str:
    """A proposal lands with its story attached: exactly one new log entry under meta/log/, whose
    seq (hex front-matter, matching the filename) is canon's seq + 1. Raises ValueError otherwise."""
    base = store.resolve_ref(prepared.into)
    # Diff the MERGE CANDIDATE against canon — the same tree conflict_preview reads. A raw
    # canon-vs-proposal-tip diff is bidirectional: when canon advances mid-review, canon's own
    # newer logs (absent from the earlier-branched proposal) read as "changed", and the count
    # refuses a log the proposer never touched (::15's recorded defect — predicted by two seats
    # before it fired). The candidate holds exactly what would land; validate that.
    logs = [p for p in store.changed_paths(base, prepared.candidate_oid) if p.startswith(LOG_DIR)]
    if len(logs) != 1:
        raise ValueError(
            f"a proposal must contain exactly one log entry under {LOG_DIR} — found {len(logs)} "
            f"({logs or 'none'}); author it with propose(domain='meta/log', slug='<seq>', type='log', seq='<seq>')")
    path = logs[0]
    env, _ = parse_entry(store.read_blob_at(prepared.candidate_oid, path).decode("utf-8", "replace"))
    seq = str(env.get("seq", "")).lower()
    try:
        n = int(seq, 16)
    except ValueError:
        raise ValueError(f"log entry {path} needs front-matter `seq` as lowercase hex, got {env.get('seq')!r}")
    stem = path[len(LOG_DIR):-3]
    if stem != seq:
        raise ValueError(f"log entry filename {stem!r} must match its seq {seq!r}")
    current, expected = canon_seq(store, origin), canon_seq(store, origin) + 1
    if n != expected:
        raise ValueError(
            f"log entry is {seq_display(n)} but canon is at {seq_display(current)} — expected {seq_display(expected)}. "
            f"Re-pull (canon_diff), reconcile, renumber the log entry, and retract the stale one (propose_retract).")
    return seq


def index_land(store, index, embedder, landed_oid: str) -> int:
    """Index ONLY what a land changed — the gate's hot path. A full reindex is O(corpus) and the
    practitioner waits on it at every stamp; a land knows its own changed paths, so the steady
    state is O(change). Position semantics match `_canon_positions` exactly: the land's paths take
    the new spine position (newest touch wins), and every older row's position is already stable
    (oldest = 1 anchoring means adding a commit shifts nothing). `reindex_from_git` remains the
    recovery / migration / model-swap path."""
    changed = store.changed_paths(f"{landed_oid}^1", landed_oid)
    spine_pos = len(store.rev_list(landed_oid))          # first-parent spine length = this land's position
    n = 0
    for path in changed:
        if not path.endswith(".md"):
            continue
        envelope, body = parse_entry(store.read_blob_at(landed_oid, path).decode("utf-8", "replace"))
        author = envelope.get("origin_author")
        if not author:                                    # the introducer, as reindex derives it
            hist = store.history(store.canon_ref, path)
            author = hist[-1]["author"] if hist else ""
        env2 = dict(envelope)
        env2["instance_depth"] = spine_pos
        index_entry(index, embedder, ref=store.canon_ref, path=path, is_canon=True,
                    authoring_instance=author, content_oid=store.blob_oid(store.canon_ref, path),
                    envelope=env2, body=body)
        n += 1
    return n


def land_and_record(store, index, embedder, audit, prepared, approval, *,
                    origin: int = CHAT_ERA_FREEZE) -> dict:
    """The practitioner's promotion routine — NOT a model-facing tool (landing is the human gate).
    Validates the proposal's log entry + seq monotonicity, lands the approved merge, audit-logs it,
    tags the merge commit state/<seq>, reindexes, and anchors the audit head into git."""
    seq = validate_log_entry(store, prepared, origin)
    r = store.land_merge(prepared, approval)
    audit.append(approval.approved_by, "land_merge", target_ref=prepared.into,
                 op_id=f"land-{r.oid[:12]}", result_oid=r.oid,
                 detail={"proposal": prepared.proposal_ref, "seq": seq})
    store.tag(f"state/{seq}", r.oid)
    index_land(store, index, embedder, r.oid)   # O(change), not O(corpus) — the gate stops waiting
    anchor = anchor_audit_head(store, audit)
    return {"landed": r.oid, "seq": seq, "display": seq_display(int(seq, 16)), "anchor": anchor}
