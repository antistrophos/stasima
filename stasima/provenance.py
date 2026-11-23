# SPDX-License-Identifier: Apache-2.0
"""
Copy with lineage — an entry's body read from another canon, and the record of where it came from.

A deployment may name other Stasima repositories as copy sources (config `copy_sources`). A write
that gives `copy_from` in place of a body has the server read the body from the source, so the text
never passes through the seat and cannot change on the way. The server reads; it never writes to a
source.

The copy carries `provenance`: a list the server writes and no seat can supply. It is a path, read
like an AS path: every place this same text has been held, the nearest first, the origin last.

    provenance: [Debut@4f1d…:technical/orientation/syntax.md, Rehearsal@9b9c…:technical/orientation/syntax-v4.md]

Each item is one address: `<Source>@<commit>:<path>` for a canon entry, `<Source>/<Seat>@<commit>:<path>`
for an entry on a seat's perspective. The commit is the full object id of the source ref's tip when
the copy was made: a pin, never a range. A copy puts the address it read at the front of the list
its source carried, and changes nothing else. So every address in the list holds this entry's body
exactly, and there is nothing to read between the items: no depth, no relation, no rule.

A name change shows in the path: the entry above is `syntax.md` now and was `syntax-v4.md` where it
came from. The path is written at every hop, changed or not, so that each address resolves alone.

Only the living edition is copied, and what it replaced is not listed here: a retirement is an act
in a canon, and its record stays in that canon. The first address leads to it.
"""
from __future__ import annotations

import re

from .authz import Denied
from .entries import parse_entry
from .local_capstore import CapStoreError, LocalCapStore, PathNotFound, PERSP_PREFIX

# The kinds of entry the server writes as the record of an act. They stay where the act happened.
SERVER_KINDS = {"msg": "a message", "vap": "a vantage", "reconciliation": "a reconcile report"}

_ADDRESS = re.compile(r"(?P<source>[^/@]+)(?:/(?P<seat>[^@]+))?@(?P<commit>[0-9a-f]{40}):(?P<path>.+)\Z", re.S)
_HOPS = 64   # a retirement chain longer than this is followed no further (and a cycle ends there)


def _md(path: str) -> str:
    return path if path.endswith(".md") else path + ".md"


def _paths(value) -> list:
    return [_md(x) for x in value if isinstance(x, str) and x] if isinstance(value, list) else []


def _quote(name: str) -> str:
    # an address is one item of a bracketed list: a comma or a closing bracket in a path or in a seat's
    # name would split or end the list when it is read back
    return name.replace("%", "%25").replace(",", "%2C").replace("]", "%5D")


def _unquote(name: str) -> str:
    return name.replace("%2C", ",").replace("%5D", "]").replace("%25", "%")


def address(source: str, seat, commit: str, path: str) -> str:
    return f"{source}{'/' + _quote(seat) if seat else ''}@{commit}:{_quote(path)}"


def _decode(raw: bytes, *, strict: bool) -> str:
    """A source file as text. A byte-order mark is not part of the entry: with it the first line is
    not `---`, the envelope reads as empty, and every rule that rests on the envelope is skipped."""
    text = raw.decode("utf-8") if strict else raw.decode("utf-8", "replace")
    return text[1:] if text.startswith("﻿") else text


def exact_body(text: str) -> str:
    """The body as the file holds it, without the frame `compose_entry` adds (the blank line after the
    envelope, the trailing whitespace). `parse_entry` strips more: the first line's indentation,
    which is content — an indented first line is a code block."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is not None:
            text = "\n".join(lines[end + 1:])
    return text.lstrip("\r\n").rstrip()


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


class _SourceStore(LocalCapStore):
    # A source is another deployment's repository and may move under this process. The pin written
    # into a copy is the tip the body was read at, so the tip is asked of git each time, not of a memo.
    REF_MEMO_TTL = 0.0


class Copied:
    """What a copy brings: the body, the source entry's envelope, and what the server will write."""
    __slots__ = ("body", "envelope", "provenance", "origin_author", "address", "source", "commit", "path")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class CopySources:
    """The sources this deployment may copy from. Read-only: ref resolution, a ref listing, blob
    reads and one path's history."""

    def __init__(self, sources: dict | None = None, *, own_name: str = "", git_timeout: float = 20.0):
        self._dirs = dict(sources or {})
        self._own = own_name
        self._timeout = git_timeout
        self._stores: dict = {}

    def names(self) -> list:
        return sorted(self._dirs)

    def _store(self, source: str) -> LocalCapStore:
        s = self._stores.get(source)
        if s is None:
            s = self._stores.setdefault(source, _SourceStore(self._dirs[source], approvers=set(),
                                                             git_timeout=self._timeout))
        return s

    @staticmethod
    def _envelope(store: LocalCapStore, commit: str, path: str):
        try:
            return parse_entry(_decode(store.read_blob_at(commit, path), strict=False))[0]
        except PathNotFound:
            return None

    @staticmethod
    def _first_writer(store: LocalCapStore, commit: str, path: str, body: str) -> str:
        """The seat on the commit that first wrote THIS body at this path, in the history that leads
        to `commit`. Not the path's introducer: a proposal can replace a path's body before it lands,
        and the text is then the second seat's. A commit the server made in its own name (author and
        committer the same) names no seat."""
        author, want = "", body.strip()
        for row in store.history(commit, path):          # newest first
            try:
                held = exact_body(_decode(store.read_blob_at(row["oid"], path), strict=False)).strip()
            except CapStoreError:
                break
            if held != want:
                break
            author = "" if row["author"] == row.get("committer") else row["author"]
        return author

    def _living(self, store: LocalCapStore, commit: str, path: str):
        """(the end of the retirement chain from `path`, whether that end is living). A chain can end
        on a retired entry whose successor is not in the tree, or turn back on itself."""
        seen = {path}
        for _ in range(_HOPS):
            env = self._envelope(store, commit, path)
            if env is None or env.get("status") != "superseded":
                return path, env is not None
            nxt = _paths(env.get("superseded_by"))
            if not nxt or nxt[0] in seen or self._envelope(store, commit, nxt[0]) is None:
                return path, False
            seen.add(nxt[0])
            path = nxt[0]
        return path, False

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
                raise Denied(f"the source {source} has no canon at {store.canon_ref}. A source's canon is read "
                             f"at that ref; check the path in the config's copy_sources, and that the "
                             f"source keeps its canon there.")
            try:
                raw = store.read_blob_at(commit, path)
            except PathNotFound:
                raise Denied(f"{where} holds no entry at {path} (at {commit[:12]}). Give the path exactly as "
                             f"the source lists it.")
            try:
                text = _decode(raw, strict=True)
            except UnicodeDecodeError:
                raise Denied(f"{where}:{path} is not valid UTF-8 at the source, so a copy would change its "
                             f"text. Nothing was written.")
            env, _ = parse_entry(text)
            if not env:
                raise Denied(f"{where}:{path} has no envelope the server can read (the file does not open "
                             f"with front matter). copy_from carries entries.")
            body = exact_body(text)
            kind = SERVER_KINDS.get(env.get("type", ""))
            if kind:
                raise Denied(f"{where}:{path} is {kind}: the server's record of an act, which stays where "
                             f"the act happened. copy_from carries authored entries.")
            if env.get("status") == "superseded":
                end, living = self._living(store, commit, path)
                fix = (f"its living edition there is {where}:{end} — copy that one; this one stays "
                       f"readable at the source" if living else
                       f"its chain ends at {where}:{end}, which is retired too and names no living "
                       f"edition in the source's tree, so there is no finished text to copy" if end != path else
                       "it names no living edition in the source's tree, so there is no finished text to copy")
                raise Denied(f"{where}:{path} is retired at the source; {fix}.")
            if not body.strip():
                raise Denied(f"{where}:{path} has an empty body; there is nothing to copy.")
            # the path the source's entry carries: where the text was held before it was held there
            carried = [str(x).strip() for x in env.get("provenance") or [] if str(x).strip()] \
                if isinstance(env.get("provenance"), list) else []
            # The true author, from the source's own record. An entry that is itself a copy keeps the
            # author it recorded, and an unknown one stays unknown: the seat that made that copy did
            # not write the text. Otherwise a perspective's entry is its seat's, and a canon entry is
            # the seat on the commit that first wrote this body (git's author field, which a seat's
            # arguments cannot set).
            author = env.get("origin_author") or ""
            if not author and not carried:
                if seat:
                    author = seat
                else:
                    try:
                        author = self._first_writer(store, commit, path, body)
                    except CapStoreError:
                        author = ""
            here = address(source, seat, commit, path)
        except PathNotFound as e:
            raise Denied(f"{where} could not be read at {path}: {e}")
        except (CapStoreError, OSError) as e:
            raise Denied(f"the source {source} cannot be read ({e.__class__.__name__}: {e}). Its repository "
                         f"is {self._dirs[source]!r} in the config's copy_sources; nothing was written.")
        return Copied(body=body, envelope=env, provenance=[here] + carried, origin_author=author, address=here,
                      source=where, commit=commit, path=path)


def read_provenance(items) -> list:
    """The path as rows, nearest first: [{source, seat, commit, path}]. An item that is not an address
    is kept as {"raw": item}: nothing recorded is dropped by a reader."""
    rows = []
    for item in items or []:
        m = _ADDRESS.match(str(item).strip())
        if not m:
            rows.append({"raw": str(item)})
            continue
        rows.append({"source": m.group("source"), "seat": _unquote(m.group("seat")) if m.group("seat") else None,
                     "commit": m.group("commit"), "path": _unquote(m.group("path"))})
    return rows
