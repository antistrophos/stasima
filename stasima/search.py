# SPDX-License-Identifier: Apache-2.0
"""
Entry search: one question, up to two legs, one ranked answer.

  - the WORD leg (lexical.py) finds entries by the words they carry, a name first;
  - the MEANING leg (the embedder's vectors) finds entries that say the same thing in other words,
    and runs only when the deployment has a real model (`embedder.semantic`).

The legs are merged by rank, not by score: a hit's fused value is the sum of 1/(K + rank) over the
legs that found it (reciprocal rank fusion). Scores from different rankers are not comparable, and
canon ::12 records that the embedder's own scores could not be given a floor; ranks need none. A
hit the word leg found by NAME stays ahead of everything else: a seat that asks for an entry by its
name is navigating, not exploring.

One body is one result. The same body held on several refs (a perspective and canon, or a carried
copy) returns once, canon's row first, with every holder listed. And canon decides whether a body
it holds is live: a body canon has retired does not come back through an unflipped copy elsewhere.
"""
from __future__ import annotations

from . import lexical

RRF_K = 60        # the usual constant: damps the gap between adjacent ranks
POOL = 5          # each leg fetches limit * POOL candidates (at least POOL_MIN): room for the body merge
POOL_MIN = 40
MAX_LIMIT = 50


def _short(ref: str, is_canon: bool) -> str:
    return "canon" if is_canon else ref.rsplit("/", 1)[-1]


def find_entries(index, embedder, query: str, *, scope: str = "all", seat: str | None = None,
                 type: str | None = None, tags=None, include_superseded: bool = False,
                 include_weak: bool = False, limit: int = 10) -> dict:
    """The answer `entry_search` returns: {results, below_floor, mode[, note]}."""
    limit = max(1, min(int(limit or 10), MAX_LIMIT))
    tags = [t.strip() for t in (tags or []) if t and t.strip()]
    words = lexical.words(query)
    status = None if include_superseded else "active"
    has_words = bool(getattr(index, "fts", False))
    has_meaning = bool(getattr(embedder, "semantic", True))
    pool = max(limit * POOL, POOL_MIN)
    common = dict(scope=scope, seat=seat, type=type, status=status, tags=tags)

    word_hits, vector_hits, below = [], [], 0
    if words and has_words:
        word_hits = index.search_words(words, limit=pool, **common)
    elif tags and not words:
        word_hits = index.tagged(tags, limit=pool, scope=scope, seat=seat, type=type, status=status)
    # the vectors rank when they carry meaning, or when there is no word index to rank instead
    if words and (has_meaning or not has_words):
        vector_hits = index.search(embedder.embed_query([query])[0], limit=pool, **common)
        floor = getattr(embedder, "score_floor", 0.0) or 0.0
        weak = [h for h in vector_hits if h.score < floor]
        if weak and not include_weak:
            vector_hits = [h for h in vector_hits if h.score >= floor]
            below = len(weak)
        if not has_meaning:
            for h in vector_hits:
                h.match = "approximate"
    mode = ("words+meaning" if has_words and has_meaning else "words" if has_words
            else "meaning" if has_meaning else "approximate")

    fused = {}                                   # (ref, path) -> [hit, fused value, similarity]
    for rank, h in enumerate(word_hits):
        fused[(h.ref, h.path)] = [h, 1.0 / (RRF_K + rank + 1), None]
    for rank, h in enumerate(vector_hits):
        e = fused.get((h.ref, h.path))
        if e:                                    # both legs found it: the word hit keeps its kind and passage
            e[1] += 1.0 / (RRF_K + rank + 1)
            e[2] = h.score
        else:
            fused[(h.ref, h.path)] = [h, 1.0 / (RRF_K + rank + 1), h.score]
    ordered = sorted(fused.values(), key=lambda e: (e[0].match != "name", -e[1]))

    def eligible(holder) -> bool:
        ref, path, is_canon, author, hstatus = holder
        if status and hstatus != status:
            return False
        return is_canon if scope == "canon" else author == (seat or "") if scope == "mine" else True

    results, seen = [], set()
    for hit, value, similarity in ordered:
        if len(results) >= limit:
            break
        key = hit.body_hash or (hit.ref, hit.path)
        if key in seen:
            continue
        seen.add(key)
        holders = index.holders_of(hit.body_hash) if hit.body_hash else []
        canon = next((h for h in holders if h[2]), None)
        if status == "active" and canon and canon[4] == "superseded":
            continue                             # canon retired this body; a stale copy does not revive it
        out = {"path": hit.path, "ref": hit.ref, "author": hit.authoring_instance, "is_canon": hit.is_canon,
               "type": hit.type, "title": hit.title, "status": hit.status, "score": round(value, 4),
               "preview": hit.preview, "match": hit.match}
        if similarity is not None:
            out["similarity"] = similarity
        shown = [h for h in holders if eligible(h)]
        if canon and eligible(canon) and not hit.is_canon:
            out.update(ref=canon[0], path=canon[1], is_canon=True, author=canon[3] or out["author"],
                       status=canon[4] or out["status"])
        if len(shown) > 1:
            out["holders"] = [_short(h[0], h[2]) if h[1] == out["path"] else f"{_short(h[0], h[2])}:{h[1]}"
                              for h in shown]
        results.append(out)

    answer = {"results": results, "below_floor": below, "mode": mode}
    if not results:
        if below:
            answer["note"] = f"{below} weak matches withheld; include_weak=true returns them"
        elif not words:
            answer["note"] = "no entry carries every one of these tags"
        elif mode == "words":
            answer["note"] = ("no entry contains these words. This deployment matches words, not meaning: "
                              "try the entry's own words, `tags`, or `term_list`")
        else:
            answer["note"] = "no entry matches"
    return answer
