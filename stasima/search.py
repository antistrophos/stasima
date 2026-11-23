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
name is navigating, not exploring. So the order of the list is the ranking; `score` is the fused
value, comparable only between results of the same `match`.

One entry is one result. An entry is a body at a path: held on several refs (a perspective and
canon, or a carried copy), it returns once, canon's row standing for it, with every holder listed.
The same body at another path is another entry, under its own name. And canon decides whether an
entry it holds is live: an entry canon has retired does not come back through an unflipped copy of
it on a perspective.

The answer is as full as the corpus allows. Copies and retired editions are removed after the legs
return, so the legs are asked again, for more, until the answer holds `limit` results or neither
leg has more to give.
"""
from __future__ import annotations

from . import lexical

RRF_K = 60        # the usual constant: damps the gap between adjacent ranks
POOL = 5          # each leg first fetches limit * POOL candidates (at least POOL_MIN)
POOL_MIN = 40
POOL_GROWTH = 4   # and this many times more on each further ask
MAX_LIMIT = 50


def _short(ref: str, is_canon: bool) -> str:
    return "canon" if is_canon else ref.rsplit("/", 1)[-1]


def _cut(hits, pool: int) -> bool:
    """Whether the limit stopped a leg. A backend that does not say is taken at its count."""
    return bool(getattr(hits, "cut", len(hits) >= pool))


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
    by_words = bool(words and has_words)
    by_tags = bool(tags and not words)
    # the vectors rank when they carry meaning, or when there is no word index to rank instead
    by_vectors = bool(words and (has_meaning or not has_words))
    mode = ("words+meaning" if has_words and has_meaning else "words" if has_words
            else "meaning" if has_meaning else "approximate")
    common = dict(scope=scope, seat=seat, type=type, status=status, tags=tags)
    index.fill_body_hashes()                     # rows a process running older code wrote since the start
    vector = embedder.embed_query([query])[0] if by_vectors else None
    floor = getattr(embedder, "score_floor", 0.0) or 0.0

    def eligible(holder) -> bool:                # may this row be shown under the ask's scope and status?
        if status and holder.status != status:
            return False
        return holder.is_canon if scope == "canon" else holder.author == (seat or "") if scope == "mine" else True

    def fits(holder) -> bool:                    # does this row itself pass the ask's type and tags?
        have = {t.lower() for t in holder.tags}
        return (not type or holder.type == type) and all(t.lower() in have for t in tags)

    pool = max(limit * POOL, POOL_MIN)
    while True:
        word_hits, vector_hits, below, more = [], [], 0, False
        if by_words:
            word_hits = index.search_words(words, limit=pool, **common)
        elif by_tags:
            word_hits = index.tagged(tags, limit=pool, scope=scope, seat=seat, type=type, status=status)
        more = _cut(word_hits, pool)
        if by_vectors:
            vector_hits = index.search(vector, limit=pool, **common)
            vector_more = _cut(vector_hits, pool)
            weak = [h for h in vector_hits if h.score < floor]
            if weak and not include_weak:
                vector_hits = [h for h in vector_hits if h.score >= floor]
                below = len(weak)
                vector_more = False              # the leg is ordered by score: past one weak hit, all are weak
            if not has_meaning:
                for h in vector_hits:
                    h.match = "approximate"
            more = more or vector_more

        fused = {}                               # (ref, path) -> [hit, fused value, similarity]
        for rank, h in enumerate(word_hits):
            fused[(h.ref, h.path)] = [h, 1.0 / (RRF_K + rank + 1), None]
        for rank, h in enumerate(vector_hits):
            e = fused.get((h.ref, h.path))
            if e:                                # both legs found it: the word hit keeps its kind and passage
                e[1] += 1.0 / (RRF_K + rank + 1)
                e[2] = h.score
            else:
                fused[(h.ref, h.path)] = [h, 1.0 / (RRF_K + rank + 1), h.score]
        ordered = sorted(fused.values(), key=lambda e: (e[0].match != "name", -e[1]))

        results, seen, retired = [], set(), 0
        for hit, value, similarity in ordered:
            if len(results) >= limit:
                break
            key = (hit.path, hit.body_hash) if hit.body_hash else (hit.ref, hit.path)
            if key in seen:
                continue
            seen.add(key)
            holders = index.holders_of(hit.body_hash, hit.path) if hit.body_hash else []
            if status == "active" and any(h.is_canon and h.status == "superseded" for h in holders):
                retired += 1                     # canon retired this entry; an unflipped copy does not revive it
                continue
            out = {"path": hit.path, "ref": hit.ref, "author": hit.authoring_instance, "is_canon": hit.is_canon,
                   "type": hit.type, "title": hit.title, "status": hit.status, "score": round(value, 4),
                   "preview": hit.preview, "match": hit.match}
            if similarity is not None:
                out["similarity"] = similarity
            shown = [h for h in holders if eligible(h)]
            lead = next((h for h in shown if h.is_canon and fits(h)), None)
            if lead and not hit.is_canon:        # canon's row stands for the entry, in its own fields
                out.update(ref=lead.ref, is_canon=True, author=lead.author or out["author"],
                           status=lead.status or out["status"], title=lead.title or out["title"],
                           type=lead.type or out["type"])
            if len(shown) > 1:
                out["holders"] = [_short(h.ref, h.is_canon) for h in shown]
            results.append(out)

        if len(results) >= limit or not more:
            break
        pool *= POOL_GROWTH                      # ends: a pool larger than the table cuts no leg

    answer = {"results": results, "below_floor": below, "mode": mode}
    if not results:
        if below:
            answer["note"] = f"{below} weak matches withheld; include_weak=true returns them"
        elif retired:
            answer["note"] = (f"{retired} matching {'entry is' if retired == 1 else 'entries are'} retired by "
                              "canon; include_superseded=true returns " + ("it" if retired == 1 else "them"))
        elif not words:
            answer["note"] = "no entry carries every one of these tags"
        elif mode == "words":
            answer["note"] = ("no entry contains these words. This deployment matches words, not meaning: "
                              "try the entry's own words, `tags`, or `term_list`")
        else:
            answer["note"] = "no entry matches"
    return answer
