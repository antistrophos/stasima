# SPDX-License-Identifier: Apache-2.0
"""
MAP index — the derived, rebuildable projection of the corpus that MAP/IMP query.

Design commitments this file honors:
  - git/audit are truth; this index is a projection, rebuildable from them.
  - one table, `authoring_instance` a DIMENSION not a partition (per-instance = a WHERE clause).
  - addressing by PATH (identity); `content_oid` recorded as a derived version pin.
  - results stay ATTRIBUTED (every Hit carries its author + layer) — never an unattributed blend.
  - IMP = entries with `recipients`; permission is index-scope (discoverability), not access-control.
    Messages live in the same table, excluded from universal search, surfaced via the recipient's inbox.
  - read-state is an append-only EVENT, never a mutable flag.

Storage and embeddings are both behind interfaces (SQLite now / Postgres later;
stub now / local-server model later) — both reversible because the index rebuilds from git.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Sequence


# ====================================================================== embeddings
class Embedder(ABC):
    model_id: str
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...   # documents (indexing side)

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        """Queries (search side). Retrieval models are often task-prefixed and embed queries
        differently from documents; the default is symmetric for embedders that don't care."""
        return self.embed(texts)


def _tokens(text: str) -> list[str]:
    return [w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if w]


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # inputs are normalized


class StubEmbedder(Embedder):
    """Deterministic, offline bag-of-hashed-tokens embedding. For dev/tests without a model server.
    It's essentially lexical similarity — enough to prove ranking/scope/index behavior reproducibly."""

    # Relevance floor for map_search: 0.0 = OFF, deliberately. Calibrated on a live ~630-entry
    # corpus (2026-07): junk-query top scores (0.28-0.30) OVERLAP true-match top scores (0.23-0.36)
    # — hashed-token cosine has no absolute meaning, so any floor here silently drops real hits.
    # A deployment may override via config `search_score_floor`; real embedders calibrate their own.
    score_floor = 0.0

    def __init__(self, dim: int = 64):
        self.dim = dim
        self.model_id = f"stub-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for tok in _tokens(t):
                bucket = int(hashlib.md5(tok.encode()).hexdigest()[:8], 16) % self.dim
                v[bucket] += 1.0
            out.append(_normalize(v))
        return out


class LocalServerEmbedder(Embedder):
    """Calls an OpenAI-compatible /v1/embeddings endpoint — LM Studio, Ollama, etc.
    Local processing, self-contained, dodges native-wheel questions (the model runs outside Python).

    Task prefixes: many retrieval models (nomic-embed-text, mxbai, snowflake-arctic, ...) are
    prefix-conditioned — documents and queries each need an instruction prefix or quality degrades
    badly (verified live: nomic without prefixes ranks related BELOW unrelated). Configure
    `doc_prefix`/`query_prefix` per model; empty strings for models that don't use them."""

    # Relevance floor for map_search: 0.0 = off until calibrated PER MODEL against a real corpus
    # (score ranges differ wildly across embedding models). Set via config `search_score_floor`
    # once a deployment has measured where its model's true/junk scores separate.
    score_floor = 0.0

    def __init__(self, base_url: str, model: str, dim: int, api_key: str = "not-needed",
                 doc_prefix: str = "", query_prefix: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_id = model
        self.dim = dim
        self.api_key = api_key
        self.doc_prefix = doc_prefix
        self.query_prefix = query_prefix

    def _post(self, texts: list[str]) -> list[list[float]]:
        import httpx

        r = httpx.post(
            f"{self.base_url}/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": texts},
            timeout=60,
        )
        r.raise_for_status()
        data = sorted(r.json()["data"], key=lambda d: d["index"])
        # normalize: the index's cosine() is a dot product, so vectors must be unit length
        # (idempotent if the model already returns normalized embeddings).
        return [_normalize(d["embedding"]) for d in data]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._post([self.doc_prefix + t for t in texts])

    def embed_query(self, texts: list[str]) -> list[list[float]]:
        return self._post([self.query_prefix + t for t in texts])


# ====================================================================== rows + hits
@dataclass
class MapRow:
    ref: str
    path: str
    is_canon: bool
    authoring_instance: str = ""
    content_oid: str = ""          # derived version pin (not authored)
    type: str = ""
    title: str = ""
    status: str = "active"
    tags: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)          # references / lineage graph
    supersedes: list[str] = field(default_factory=list)    # declared succession edges (lineage graph)
    region_labels: list[str] = field(default_factory=list)  # maps
    links: list[str] = field(default_factory=list)          # maps; or message coordinates
    salience: float = 0.0                                    # maps
    recipients: list[str] = field(default_factory=list)     # messages
    subject: str = ""                                        # messages
    vantage: str = ""                                        # vantages: provenance (confirmed | reconstructed-by-X)
    canon_state: str = ""                                    # the canon oid the act was figured against (pinned at write)
    instance_depth: int = 0                                  # mechanical per-ref commit position (pinned at write; 0 = unpinned)
    tick: str = ""                                           # state updates: the DECLARED label's mirror field (hex; optional forever; prose governs)
    thread: str = ""                                         # reserved associative tag (ref-safe form; value semantics unruled — reserve-the-field-rule-the-values)
    body_text: str = ""
    embedding: list[float] = field(default_factory=list)
    model_id: str = ""


@dataclass
class Hit:
    path: str
    ref: str
    authoring_instance: str
    is_canon: bool
    type: str
    title: str
    score: float
    preview: str
    status: str = "active"   # rides every hit so a deliberately-included retired edition is apparent


# ====================================================================== index interface
class MapIndex(ABC):
    """The thin storage seam. SQLite now; a Postgres+pgvector backend implements the same ABC later."""

    @abstractmethod
    def upsert(self, row: MapRow) -> None: ...

    @abstractmethod
    def search(self, query_embedding: list[float], *, scope: str = "all",
               instance_id: Optional[str] = None, type: Optional[str] = None,
               status: str = "active", limit: int = 10) -> list[Hit]: ...

    @abstractmethod
    def cartography_of(self, target_path: str) -> list[MapRow]: ...   # Q4 raw material

    @abstractmethod
    def inbox(self, instance_id: str) -> list[MapRow]: ...   # all messages addressed to instance_id

    @abstractmethod
    def vantages_for(self, *, entry=None, author=None, canon_state=None) -> list[MapRow]: ...   # VAP projection

    @abstractmethod
    def authors_of(self, path: str) -> set: ...   # whose entry is this, across refs — for the confirmed check

    @abstractmethod
    def authors_of_body(self, body: str) -> dict: ...   # {author: exemplar path} for a VERBATIM body — the cross-propose guard's second axis

    @abstractmethod
    def threads(self) -> dict: ...   # {tag: {count, authors, latest}} over declared thread= — the scry registry

    @abstractmethod
    def thread_entries(self, tag: str, limit: int = 16, offset: int = 0): ...   # (rows newest-first, total) for one tag

    @abstractmethod
    def arg_terms(self) -> dict: ...   # the dictionary registry: {term: {definitions, trees, canon}} over type='arg'

    @abstractmethod
    def arg_definitions(self, term: str) -> list: ...   # one term's DISTINCT definitions, holders annotated (echo-collapse)

    @abstractmethod
    def envelopes_for(self, ref: str) -> dict: ...   # {path: {title,status,type}} — listing enrichment, one query

    @abstractmethod
    def status_of(self, path: str) -> str: ...   # the entry's status wherever it lives (canon preferred)

    @abstractmethod
    def clear(self) -> None: ...   # for a full rebuild from git


# ====================================================================== sqlite backend
_COLS = ["ref", "path", "is_canon", "authoring_instance", "content_oid", "type", "title",
         "status", "tags", "refs", "supersedes", "region_labels", "links", "salience", "recipients",
         "subject", "vantage", "canon_state", "instance_depth", "tick", "thread", "body_text", "embedding", "model_id"]
_JSON_COLS = {"tags", "refs", "supersedes", "region_labels", "links", "recipients", "embedding"}


class SqliteMapIndex(MapIndex):
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS map_entries (
                ref TEXT NOT NULL, path TEXT NOT NULL, is_canon INTEGER NOT NULL,
                authoring_instance TEXT, content_oid TEXT, type TEXT, title TEXT, status TEXT,
                tags TEXT, refs TEXT, supersedes TEXT, region_labels TEXT, links TEXT, salience REAL,
                recipients TEXT, subject TEXT, vantage TEXT, canon_state TEXT, instance_depth INTEGER,
                tick TEXT, thread TEXT, body_text TEXT, embedding TEXT, model_id TEXT,
                PRIMARY KEY (ref, path)
            );
            CREATE INDEX IF NOT EXISTS ix_author ON map_entries(authoring_instance);
            CREATE INDEX IF NOT EXISTS ix_canon  ON map_entries(is_canon);
            CREATE INDEX IF NOT EXISTS ix_type   ON map_entries(type);
            """
        )
        # additive migration: an index built before VAP lacks these columns — CREATE TABLE IF NOT EXISTS
        # leaves an existing table untouched, so ALTER-add them (the table is a rebuildable cache, but this
        # keeps a live deployment usable without a forced delete + reindex). This MUST precede any index on
        # the new columns, or the index creation hits 'no such column' on a pre-VAP db.
        have = {r["name"] for r in self.conn.execute("PRAGMA table_info(map_entries)")}
        for col, sqltype in (("vantage", "TEXT"), ("canon_state", "TEXT"), ("instance_depth", "INTEGER"),
                             ("supersedes", "TEXT"), ("tick", "TEXT"), ("thread", "TEXT")):
            if col not in have:
                self.conn.execute(f"ALTER TABLE map_entries ADD COLUMN {col} {sqltype}")
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_cstate ON map_entries(canon_state)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_idepth ON map_entries(instance_depth)")
        self.conn.commit()

    def upsert(self, row: MapRow) -> None:
        vals = []
        for c in _COLS:
            v = getattr(row, c)
            if c == "is_canon":
                v = 1 if v else 0
            elif c in _JSON_COLS:
                v = json.dumps(v)
            vals.append(v)
        ph = ",".join("?" * len(_COLS))
        self.conn.execute(f"INSERT OR REPLACE INTO map_entries ({','.join(_COLS)}) VALUES ({ph})", vals)
        self.conn.commit()

    def _row(self, r: sqlite3.Row) -> MapRow:
        d = {c: r[c] for c in _COLS}
        d["is_canon"] = bool(d["is_canon"])
        d["instance_depth"] = int(d["instance_depth"] or 0)   # pre-pin rows carry NULL — 0 means unpinned
        d["tick"] = d["tick"] or ""                           # pre-field rows carry NULL — absence is normal
        d["thread"] = d["thread"] or ""
        for c in _JSON_COLS:
            d[c] = json.loads(d[c]) if d[c] else ([] )
        return MapRow(**d)

    def search(self, query_embedding, *, scope="all", instance_id=None, type=None, status="active", limit=10):
        # universal search excludes the index-scoped types (messages, vantages); they surface only via
        # their own scoped lookups (inbox / vap_for). INVARIANT: any new universal-retrieval path (e.g. a
        # future lexical/fusion ranker) MUST inherit this exclusion, or it re-admits the echo it must not.
        where = ["type NOT IN ('msg', 'vap')"]
        params: list = []
        if status:
            where.append("status = ?"); params.append(status)
        if type:
            where.append("type = ?"); params.append(type)
        if scope == "canon":
            where.append("is_canon = 1")
        elif scope == "mine":
            where.append("authoring_instance = ?"); params.append(instance_id or "")
        sql = "SELECT * FROM map_entries WHERE " + " AND ".join(where)
        scored = []
        for r in self.conn.execute(sql, params).fetchall():
            row = self._row(r)
            if not row.embedding:
                continue
            scored.append((cosine(query_embedding, row.embedding), row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            Hit(path=row.path, ref=row.ref, authoring_instance=row.authoring_instance,
                is_canon=row.is_canon, type=row.type, title=row.title,
                score=round(s, 4), preview=row.body_text[:160], status=row.status)
            for s, row in scored[:limit]
        ]

    def cartography_of(self, target_path):
        rows = [self._row(r) for r in self.conn.execute("SELECT * FROM map_entries WHERE type='map'").fetchall()]
        return [r for r in rows if target_path in r.links]

    def inbox(self, instance_id):
        rows = [self._row(r) for r in self.conn.execute("SELECT * FROM map_entries WHERE type='msg'").fetchall()]
        return [r for r in rows if instance_id in r.recipients]   # read-state lives in the audit log

    def vantages_for(self, *, entry=None, author=None, canon_state=None):
        """Reverse-bound projection over vantages (type='vap') — the second layer on a search result.
        By `entry` (the set bound to it: one author over canon-states = melody, many authors at one
        canon-state = harmony), by `author` (one thread), by `canon_state` (a cross-instance slice).
        Vantages are excluded from search(); this scoped lookup is the only way they surface."""
        where, params = ["type = 'vap'"], []
        if author:
            where.append("authoring_instance = ?"); params.append(author)
        if canon_state:
            where.append("canon_state = ?"); params.append(canon_state)
        # newest-first ordering depends on the projection: instance_depth is a PER-REF clock, so it
        # orders a single author's thread truly (pinned rows first, rowid for the pre-pin past) but is
        # meaningless ACROSS refs — a verbose author's depths would bury a fresh seat's newer vantage.
        # Cross-ref projections (entry/canon_state/all) use rowid DESC: insertion order for
        # inline-indexed writes — an honest global recency proxy until a globally comparable
        # write-time column exists (a reindex rebuilds rowids in path order; marked, not hidden).
        order = (" ORDER BY (instance_depth IS NULL), instance_depth DESC, rowid DESC" if author
                 else " ORDER BY rowid DESC")
        rows = [self._row(r) for r in
                self.conn.execute("SELECT * FROM map_entries WHERE " + " AND ".join(where) + order,
                                  params).fetchall()]
        if entry:
            rows = [r for r in rows if entry in r.links]   # reverse-binding: the vantage points AT the entry
        return rows

    def authors_of(self, path):
        """Every authoring_instance holding an entry at `path` (across refs). Provenance survives
        promotion, so this answers 'whose entry is this?' for the confirmed-vantage dignity check."""
        return {r["authoring_instance"] for r in
                self.conn.execute("SELECT DISTINCT authoring_instance FROM map_entries WHERE path = ?", (path,))}

    def authors_of_body(self, body):
        """{authoring_instance: exemplar path} for every seat holding this VERBATIM body (stripped —
        the same normalization the immutability guard compares by). Exact match only, deliberately:
        a byte-identical body is a FACT machinery can hold; a near-match is a judgment about whose
        idea something is, which is usage, not structure. The cross-propose guard's second axis —
        path-match alone is bypassable by renaming the slug."""
        ws = " " + chr(10) + chr(13) + chr(9)
        out = {}
        for r in self.conn.execute(
                "SELECT authoring_instance, path FROM map_entries "
                "WHERE TRIM(body_text, ?) = ? AND authoring_instance != ''", (ws, body.strip())):
            out.setdefault(r["authoring_instance"], r["path"])
        return out

    def threads(self):
        """{tag: {count, authors, latest}} over every declared thread= — the scry registry.
        Declared tags only; a homonym collision shows here as one tag with surprising authors,
        which is exactly the curation catch the values-open era wants visible."""
        out = {}
        for r in self.conn.execute(
                "SELECT thread, COUNT(*) AS n FROM map_entries WHERE thread != '' GROUP BY thread"):
            out[r["thread"]] = {"count": r["n"]}
        for tag in out:
            auth = [x["authoring_instance"] for x in self.conn.execute(
                "SELECT DISTINCT authoring_instance FROM map_entries WHERE thread = ?", (tag,))]
            last = self.conn.execute(
                "SELECT path, ref FROM map_entries WHERE thread = ? ORDER BY rowid DESC LIMIT 1",
                (tag,)).fetchone()
            out[tag]["authors"] = sorted(a for a in auth if a)
            out[tag]["latest"] = {"path": last["path"], "ref": last["ref"]} if last else None
        return out

    def thread_entries(self, tag, limit=16, offset=0):
        """One tag's rows, newest-indexed-first, bounded — plus the total for honest truncation."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM map_entries WHERE thread = ?", (tag,)).fetchone()[0]
        rows = [self._row(r) for r in self.conn.execute(
            "SELECT * FROM map_entries WHERE thread = ? ORDER BY rowid DESC LIMIT ? OFFSET ?",
            (tag, limit, offset))]
        return rows, total

    def arg_terms(self):
        """The dictionary registry: {term: {definitions, trees, canon}} over every type='arg' row.
        A term is its path stem; a DEFINITION is a distinct stripped body. One term with several
        definitions is divergence to read; one definition echoed across trees is concordance."""
        out = {}
        for r in self.conn.execute("SELECT path, ref, is_canon, body_text FROM map_entries WHERE type = 'arg'"):
            stem = r["path"].rsplit("/", 1)[-1]
            term = stem[:-3] if stem.endswith(".md") else stem
            e = out.setdefault(term, {"defs": set(), "trees": set(), "canon": False})
            e["defs"].add((r["body_text"] or "").strip())
            e["trees"].add(r["ref"])
            e["canon"] = e["canon"] or bool(r["is_canon"])
        return {t: {"definitions": len(e["defs"]), "trees": sorted(e["trees"]), "canon": e["canon"]}
                for t, e in sorted(out.items())}

    def arg_definitions(self, term):
        """One term's DISTINCT definitions, each shown once, every holder annotated — the
        concordance-vs-divergence view: echo-collapsing by provenance, at path-length zero.
        Canon-held definitions sort first, then by echo count. All editions shown WITH status."""
        defs = {}
        for r in self.conn.execute(
                "SELECT path, ref, authoring_instance, is_canon, status, body_text FROM map_entries "
                "WHERE type = 'arg' AND (path LIKE ? OR path = ?)", (f"%/{term}.md", f"{term}.md")):
            key = (r["body_text"] or "").strip()
            d = defs.setdefault(key, {"preview": key[:240], "canon": False, "holders": []})
            d["canon"] = d["canon"] or bool(r["is_canon"])
            d["holders"].append({"ref": r["ref"], "author": r["authoring_instance"],
                                 "path": r["path"], "status": r["status"] or ""})
        ordered = sorted(defs.values(), key=lambda d: (not d["canon"], -len(d["holders"]), d["preview"]))
        for d in ordered:
            d["holders"].sort(key=lambda h: h["ref"])
        return ordered

    def envelopes_for(self, ref):
        """Envelope pointers (title/status/type, + tick where a state update declared one) for every
        indexed entry under `ref` — ONE query, so listings can be enriched without N per-path git
        reads. The index is a derived cache: a path it doesn't know simply gets empty fields; git
        remains the truth of WHICH paths exist. `tick` rides only when present — absence is normal
        and means nothing (two-clock conventions v3, clause 1)."""
        return {r["path"]: {"title": r["title"] or "", "status": r["status"] or "", "type": r["type"] or "",
                            **({"tick": r["tick"]} if r["tick"] else {}),
                            **({"thread": r["thread"]} if r["thread"] else {})}
                for r in self.conn.execute(
                    "SELECT path, title, status, type, tick, thread FROM map_entries WHERE ref = ?", (ref,))}

    def status_of(self, path):
        """The entry's status wherever the path lives, canon edition preferred — for resolving a
        binding whose target sits on ANOTHER ref (a reconstructed vantage binds someone else's entry)."""
        r = self.conn.execute(
            "SELECT status FROM map_entries WHERE path = ? ORDER BY is_canon DESC LIMIT 1", (path,)).fetchone()
        return (r["status"] or "") if r else ""

    def clear(self):
        self.conn.execute("DELETE FROM map_entries")
        self.conn.commit()


# ====================================================================== inline indexer
def index_entry(index: MapIndex, embedder: Embedder, *, ref: str, path: str, is_canon: bool,
                authoring_instance: str, content_oid: str, envelope: dict, body: str) -> MapRow:
    """The single-process server calls this inline on each commit. Truth stays in git;
    this writes the derived row. Cartographic prose / titles + body are what get embedded."""
    embed_text = " ".join(filter(None, [envelope.get("title", ""), body]))
    emb = embedder.embed([embed_text])[0]
    row = MapRow(
        ref=ref, path=path, is_canon=is_canon, authoring_instance=authoring_instance, content_oid=content_oid,
        type=envelope.get("type", ""), title=envelope.get("title", ""), status=envelope.get("status", "active"),
        tags=envelope.get("tags", []), refs=envelope.get("references", []),
        supersedes=envelope.get("supersedes", []),
        region_labels=envelope.get("region_labels", []),
        links=envelope.get("links", envelope.get("coordinates", [])),
        salience=float(envelope.get("salience", 0.0)),
        recipients=envelope.get("recipients", []), subject=envelope.get("subject", ""),
        vantage=envelope.get("vantage", ""), canon_state=envelope.get("canon_state", ""),
        instance_depth=int(envelope.get("instance_depth", 0) or 0),   # str after a reindex's parse_entry
        tick=str(envelope.get("tick", "") or ""),                     # the mirror field, surfaced verbatim
        thread=str(envelope.get("thread", "") or ""),                 # the reserved associative tag
        body_text=body, embedding=emb, model_id=embedder.model_id,
    )
    index.upsert(row)
    return row
