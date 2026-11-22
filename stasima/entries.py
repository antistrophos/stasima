# SPDX-License-Identifier: Apache-2.0
"""
Entry serialization — the content-model's YAML-front-matter + body format.

Shared by the server (compose on write, parse on reindex) and the orientation renderer (parse to
render sections). Minimal on purpose: legible in git; the indexer is fed the envelope dict directly,
so compose is the only direction that must round-trip for v1.
"""


# The envelope fields whose value is a list. Only these read back as a list: a title or a subject
# may begin "[" and end "]" ("[draft] A rule [v2]") and is still one string. Read every bracketed
# value as a list and such a title becomes one — the index then refuses the row, at a land after
# canon has moved and at every rebuild after it. A new list field is added here when it is written.
LIST_KEYS = frozenset({"tags", "references", "supersedes", "superseded_by", "recipients",
                       "coordinates", "region_labels", "links"})


def _flat(v) -> str:
    # envelope values are single-line by construction: a newline in a title/subject/tag would
    # otherwise inject arbitrary front-matter fields (e.g. a forged seq or status)
    return " ".join(str(v).splitlines())


def compose_entry(envelope: dict, body: str) -> str:
    lines = ["---"]
    for k, v in envelope.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(_flat(x) for x in v)}]")
        else:
            lines.append(f"{k}: {_flat(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.rstrip() + "\n"


def parse_entry(text: str):
    """Inverse of compose_entry (our minimal front-matter). Returns (envelope_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    env = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k in LIST_KEYS and v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            env[k] = [x.strip() for x in inner.split(",")] if inner else []
        else:
            env[k] = v
    return env, parts[2].strip()
