# SPDX-License-Identifier: Apache-2.0
"""
Copy with lineage — an entry's body read from another canon, and the record of where it came from.

A deployment may name other Stasima repositories as copy sources (config `copy_sources`). A write
that gives `copy_from` in place of a body has the server read the body from the source, so the text
never passes through the seat and cannot change on the way. The server reads; it never writes to a
source.

The copy carries `provenance`: a list the server writes and no seat can supply. Each item is one
ancestor of the entry, as

    <depth> <relation> <address>

`address` is `<Source>@<commit>:<path>` for a canon entry and `<Source>/<Seat>@<commit>:<path>` for
an entry on a seat's perspective. The commit is the full object id of the source ref's tip when the
copy was made: a pin, never a range. `relation` is `copy of` (the same body, held there) or
`supersedes` (the earlier edition it replaced there). `depth` nests the list: depth 1 is this
entry's own source, and an item at depth n+1 describes the nearest item above it at depth n. So

    provenance: [1 copy of Rehearsal@9b9c…:technical/skill-v2.md, 2 supersedes Rehearsal@9b9c…:technical/skill.md]

reads: this entry is a copy of skill-v2 in Rehearsal, which superseded skill there. A copy of a
copy keeps the whole list one level deeper, so the sourcing survives any number of copies. The
envelope stays one value per line; the nesting is in the numbers.

Only the living edition is copied. Its earlier editions stay at the source and are named here, each
at the same pinned commit, where the source still holds them.
"""
from __future__ import annotations

import re
import threading

from .authz import Denied
from .entries import parse_entry
from .local_capstore import CapStoreError, LocalCapStore, PathNotFound, PERSP_PREFIX

# The kinds of entry the server writes as the record of an act. They stay where the act happened.
SERVER_KINDS = {"msg": "a message", "vap": "a vantage", "reconciliation": "a reconcile report"}

_ITEM = re.compile(r"(\d+) (.+)\Z", re.S)
_HOPS = 64   # a retirement chain longer than this is followed no further (and a cycle ends there)


def _md(path: str) -> str:
    return path if path.endswith(".md") else path + ".md"


def _paths(value) -> list:
    return [_md(x) for x in value if isinstance(x, str) and x] if isinstance(value, list) else []


def _quote(path: str) -> str:
    # an address is one item of a bracketed list: a comma or a closing bracket in a path would split
    # or end the list when it is read back
    return path.replace("%", "%25").replace(",", "%2C").replace("]", "%5D")


def address(source: str, seat, commit: str, path: str) -> str:
    return f"{source}{'/' + seat if seat else ''}@{commit}:{_quote(path)}"


def parse_copy_from(text: str):
    """`Source:path` or `Source/Seat:path` -> (source, seat or None, path)."""
    head, sep, path = (text or "").strip().partition(":")
    source, slash, seat = head.partition("/")
    path = path.strip().lstrip("/")
    if not sep or not source or not path or (slash and not seat) or "@" in head:
        raise Denied(f"copy_from={text!r} must be '<Source>:<path>' for a canon entry or "
                     f"'<Source>/<Seat>:<path>' for an entry on a seat's perspective, with the path as "
                     f"the source lists it (the server pins the commit; give none)")
    return source.strip(), (seat.strip() or None) if slash else None, _md(path)


class Copied:
    """What a copy brings: the body, the source entry's envelope, and what the server will write."""
    __slots__ = ("body", "envelope", "provenance", "origin_author", "address", "source", "commit", "path")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class CopySources:
    """The sources this deployment may copy from. Read-only: ref resolution, tree listing, blob reads."""

    def __init__(self, sources: dict | None = None, *, own_name: str = "", git_timeout: float = 20.0):
        self._dirs = dict(sources or {})
        self._own = own_name
        self._timeout = git_timeout
        self._stores: dict = {}
        self._trees: dict = {}      # (source, commit) -> {path: brief envelope}
        self._lock = threading.Lock()

    def names(self) -> list:
        return sorted(self._dirs)

    def _store(self, source: str) -> LocalCapStore:
        with self._lock:
            s = self._stores.get(source)
            if s is None:
                s = self._stores[source] = LocalCapStore(self._dirs[source], approvers=set(),
                                                         git_timeout=self._timeout)
            return s

    def _tree(self, source: str, store: LocalCapStore, commit: str) -> dict:
        """Every entry in the source's tree at `commit`, reduced to the fields a chain needs, with each
        entry's earlier editions resolved from both sides of the pair. Built once per pinned commit."""
        key = (source, commit)
        with self._lock:
            hit = self._trees.get(key)
        if hit is not None:
            return hit
        tree = {}
        for path in store.list_paths(commit):
            if not path.endswith(".md"):
                continue
            env, _ = parse_entry(store.read_blob_at(commit, path).decode("utf-8", "replace"))
            tree[path] = {"status": env.get("status", ""),
                          "supersedes": _paths(env.get("supersedes")),
                          "superseded_by": _paths(env.get("superseded_by")),
                          "provenance": env.get("provenance") if isinstance(env.get("provenance"), list) else [],
                          "earlier": []}
        for path, e in tree.items():           # the edge the new edition declares
            for x in e["supersedes"]:
                if x in tree and x != path and x not in e["earlier"]:
                    e["earlier"].append(x)
        for path in sorted(tree):               # the edge the retired edition declares (the one the server follows)
            e = tree[path]
            if e["status"] == "superseded" and e["superseded_by"]:
                nxt = e["superseded_by"][0]
                if nxt in tree and nxt != path and path not in tree[nxt]["earlier"]:
                    tree[nxt]["earlier"].append(path)
        with self._lock:
            if len(self._trees) > 64:
                self._trees.clear()
            self._trees[key] = tree
        return tree

    @staticmethod
    def _living(tree: dict, path: str) -> str:
        seen = {path}
        for _ in range(_HOPS):
            e = tree.get(path)
            if not e or e["status"] != "superseded" or not e["superseded_by"]:
                break
            nxt = e["superseded_by"][0]
            if nxt in seen or nxt not in tree:
                break
            seen.add(nxt)
            path = nxt
        return path

    def _ancestry(self, tree, source, seat, commit, path, depth, seen, out):
        e = tree[path]
        for item in e["provenance"]:            # it was itself a copy: its sources sit one level under it
            m = _ITEM.match(str(item).strip())
            out.append(f"{depth + int(m.group(1))} {m.group(2)}" if m else f"{depth + 1} {str(item).strip()}")
        if depth >= _HOPS:
            return
        for earlier in e["earlier"]:
            if earlier in seen:
                continue
            seen.add(earlier)
            out.append(f"{depth + 1} supersedes {address(source, seat, commit, earlier)}")
            self._ancestry(tree, source, seat, commit, earlier, depth + 1, seen, out)

    def read(self, copy_from: str) -> Copied:
        source, seat, path = parse_copy_from(copy_from)
        if source not in self._dirs:
            known = ", ".join(self.names()) or "none (the config's copy_sources names them)"
            own = (f" {source!r} is this deployment: copy_from reads another canon; inside this one, "
                   f"propose the entry with origin_author.") if self._own and source == self._own else ""
            raise Denied(f"copy_from names the source {source!r}; this deployment's copy sources: {known}.{own}")
        store = self._store(source)
        ref = PERSP_PREFIX + seat if seat else store.canon_ref
        where = f"{source}/{seat}" if seat else source
        try:
            if seat:
                # the listing, not a ref lookup: on a filesystem that ignores case a lookup of 'wren'
                # finds 'Wren', and the copy would record a name no seat has
                names = [r.name[len(PERSP_PREFIX):] for r in store.list_refs(PERSP_PREFIX)]
                if seat not in names:
                    near = [n for n in names if n.casefold() == seat.casefold()]
                    raise Denied(f"the source {source} has no perspective named {seat!r}"
                                 + (f"; it has {near[0]!r}. Seat names are exact, case included."
                                    if near else ". Seat names are exact, case included."))
            commit = store.resolve_ref(ref)
            if commit is None:
                raise Denied(f"the source {source} has no canon at {store.canon_ref} — check its path in the "
                             f"config's copy_sources")
            tree = self._tree(source, store, commit)
            if path not in tree:
                raise Denied(f"{where} holds no entry at {path} (at {commit[:12]}). Give the path exactly as "
                             f"the source lists it.")
            env, body = parse_entry(store.read_blob_at(commit, path).decode("utf-8", "replace"))
            kind = SERVER_KINDS.get(env.get("type", ""))
            if kind:
                raise Denied(f"{where}:{path} is {kind}: the server's record of an act, which stays where "
                             f"the act happened. copy_from carries authored entries.")
            if env.get("status") == "superseded":
                living = self._living(tree, path)
                fix = (f"its living edition there is {where}:{living} — copy that one; its provenance "
                       f"will name this one" if living != path else
                       "it names no living edition in the source's tree, so there is no finished text to copy")
                raise Denied(f"{where}:{path} is retired at the source; {fix}.")
            if not body.strip():
                raise Denied(f"{where}:{path} has an empty body; there is nothing to copy.")
            # The true author, from the source's own record. An entry that is itself a copy keeps the
            # author it recorded, and an unknown one stays unknown: the seat that made that copy did
            # not write the text. Otherwise a perspective's entry is its seat's, and a canon entry is
            # the seat named on the commit that introduced the path (a bootstrap commit names none).
            author = env.get("origin_author") or ""
            if not author and not env.get("provenance"):
                if seat:
                    author = seat
                else:
                    try:
                        hist = store.history(commit, path)
                        author = (store._trailer(hist[-1]["oid"], "instance-id") or "") if hist else ""
                    except CapStoreError:
                        author = ""
            here = address(source, seat, commit, path)
            items = [f"1 copy of {here}"]
            self._ancestry(tree, source, seat, commit, path, 1, {path}, items)
        except PathNotFound as e:
            raise Denied(f"{where} could not be read at {path}: {e}")
        except (CapStoreError, OSError) as e:
            raise Denied(f"the source {source} cannot be read ({e.__class__.__name__}: {e}). Its repository "
                         f"is {self._dirs[source]!r} in the config's copy_sources; nothing was written.")
        return Copied(body=body, envelope=env, provenance=items, origin_author=author, address=here,
                      source=where, commit=commit, path=path)


def read_provenance(items) -> list:
    """The outline as rows: [{depth, relation, address}], for a reader that wants the structure."""
    rows = []
    for item in items or []:
        m = _ITEM.match(str(item).strip())
        if not m:
            continue
        rest = m.group(2)
        for rel in ("copy of", "supersedes"):
            if rest.startswith(rel + " "):
                rows.append({"depth": int(m.group(1)), "relation": rel, "address": rest[len(rel) + 1:]})
                break
    return rows
