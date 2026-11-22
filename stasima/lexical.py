# SPDX-License-Identifier: Apache-2.0
"""
The word index: the lexical leg of entry search.

A full-text table (SQLite FTS5) kept beside `map_entries` in the same database file. It answers the
question the embedder cannot: "which entry carries this NAME?" A word in a path, a title, or a tag
outranks the same word in a body, and the query found as a phrase in one of those name-bearing
fields ranks first of all.

Design commitments:
  - It is part of the map index, so it is a rebuildable projection of git like the rest.
  - The database keeps it current, not the calling code: three triggers on `map_entries` mirror
    every insert, delete, and change. A process running older code still feeds it.
  - It holds only what universal search may return. Messages and vantages never enter it, and the
    search query filters them again on the way out.
  - A SQLite build without FTS5 is not an error: `setup` returns False and search falls back to
    the embedder alone.
"""
from __future__ import annotations

import sqlite3
import unicodedata

TABLE = "map_fts"
# column order is the table's; a weight ranks a word in that column against the same word in a body
COLUMNS = ("path", "title", "tags", "thread", "body")
WEIGHTS = (6.0, 10.0, 8.0, 3.0, 1.0)
NAME_FIELDS = "{path title tags}"     # where an entry's name lives
BODY_COLUMN = COLUMNS.index("body")
MAX_TERMS = 48                        # distinct words taken from one query
MAX_PHRASE = 12                       # a longer query is a description, not a name
SEARCHABLE = "COALESCE({a}type, '') NOT IN ('msg', 'vap')"

_VALUES = ("{r}.rowid, {r}.path, COALESCE({r}.title, ''), COALESCE({r}.tags, ''), "
           "COALESCE({r}.thread, ''), COALESCE({r}.body_text, '')")


def setup(conn: sqlite3.Connection) -> bool:
    """Create the table and its triggers if absent, then bring the table level with
    `map_entries`. Returns False when this SQLite build has no FTS5."""
    try:
        conn.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS {TABLE} USING fts5("
                     f"{', '.join(COLUMNS)}, tokenize='porter unicode61 remove_diacritics 2')")
    except sqlite3.OperationalError:
        return False
    cols = ", ".join(COLUMNS)
    new_ok = SEARCHABLE.format(a="new.")
    conn.executescript(f"""
        CREATE TRIGGER IF NOT EXISTS {TABLE}_ai AFTER INSERT ON map_entries BEGIN
            DELETE FROM {TABLE} WHERE rowid = new.rowid;
            INSERT INTO {TABLE}(rowid, {cols}) SELECT {_VALUES.format(r='new')} WHERE {new_ok};
        END;
        CREATE TRIGGER IF NOT EXISTS {TABLE}_ad AFTER DELETE ON map_entries BEGIN
            DELETE FROM {TABLE} WHERE rowid = old.rowid;
        END;
        CREATE TRIGGER IF NOT EXISTS {TABLE}_au
        AFTER UPDATE OF path, title, tags, thread, body_text, type ON map_entries BEGIN
            DELETE FROM {TABLE} WHERE rowid = old.rowid;
            INSERT INTO {TABLE}(rowid, {cols}) SELECT {_VALUES.format(r='new')} WHERE {new_ok};
        END;
    """)
    sync(conn)
    return True


def sync(conn: sqlite3.Connection) -> None:
    """Level the table with `map_entries`: drop rows whose entry is gone, add entries it lacks.
    Runs at every start, so an index written before the table existed fills itself, and rows
    left behind by a process that predates the triggers are cleared. One transaction; a database
    busy with another process is left for the next start (the triggers keep new writes indexed)."""
    ok = SEARCHABLE.format(a="")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"DELETE FROM {TABLE} WHERE rowid NOT IN (SELECT rowid FROM map_entries WHERE {ok})")
        conn.execute(f"INSERT INTO {TABLE}(rowid, {', '.join(COLUMNS)}) "
                     f"SELECT {_VALUES.format(r='map_entries')} FROM map_entries "
                     f"WHERE {ok} AND rowid NOT IN (SELECT rowid FROM {TABLE})")
        conn.commit()
    except sqlite3.Error:
        conn.rollback()


def clear(conn: sqlite3.Connection) -> None:
    conn.execute(f"DELETE FROM {TABLE}")


def words(query: str) -> list[str]:
    """The query as the tokenizer will see it: runs of letters and digits, lowercased, in order.
    A combining mark stays with the letter it follows, as the tokenizer keeps it: a query typed
    decomposed, or a capital whose lowercase is a letter plus a mark, is still one word (the
    tokenizer folds the mark away on both sides, so composed and decomposed spellings meet).
    Everything else is a separator, which is also what makes the words safe to place in a MATCH
    expression: nothing the caller typed survives except letters, digits, and their marks."""
    out, word = [], []
    for ch in (query or "").lower():
        if ch.isalnum() or (word and unicodedata.category(ch).startswith("M")):
            word.append(ch)
        elif word:
            out.append("".join(word))
            word = []
    if word:
        out.append("".join(word))
    return out


def _passes(raw: list[str]) -> list[tuple[str, str]]:
    """The three questions asked of the table, strongest first. Each is (match kind, expression)."""
    distinct = list(dict.fromkeys(raw))[:MAX_TERMS]
    quoted = ['"' + t + '"' for t in distinct]
    out = []
    if len(raw) <= MAX_PHRASE:
        out.append(("name", f'{NAME_FIELDS} : "{" ".join(raw)}"'))
    out.append(("all-words", " AND ".join(quoted)))
    if len(distinct) > 1:
        out.append(("some-words", " OR ".join(quoted)))
    return out


def search(conn: sqlite3.Connection, raw: list[str], where: str, params: list, limit: int) -> tuple:
    """Ranked rows for the query words, and whether the limit cut them: ([(row, match kind,
    passage)], cut), best first. `where` filters `map_entries` (aliased `e`) and must itself
    exclude the unsearchable types. Within a pass the order is BM25 with the column weights; a row
    keeps the kind of the first pass that found it. `cut` is True when a larger limit may return
    more: a pass filled the limit, or a pass did not run because earlier ones had."""
    if not raw:
        return [], False
    weights = ", ".join(str(w) for w in WEIGHTS)
    sql = (f"SELECT e.rowid AS _rowid, e.*, "
           f"snippet({TABLE}, {BODY_COLUMN}, '', '', ' … ', 28) AS _passage "
           f"FROM {TABLE} JOIN map_entries e ON e.rowid = {TABLE}.rowid "
           f"WHERE {TABLE} MATCH ? AND {where} "
           f"ORDER BY bm25({TABLE}, {weights}), e.is_canon DESC, e.ref, e.path LIMIT ?")
    out, seen, cut = [], set(), False
    for kind, expression in _passes(raw):
        if len(out) >= limit:
            cut = True
            break
        rows = conn.execute(sql, [expression, *params, limit]).fetchall()
        cut = cut or len(rows) >= limit
        for r in rows:
            if r["_rowid"] not in seen:
                seen.add(r["_rowid"])
                out.append((r, kind, " ".join((r["_passage"] or "").split())))
    return out[:limit], cut or len(out) > limit
