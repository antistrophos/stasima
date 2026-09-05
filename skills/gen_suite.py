# SPDX-License-Identifier: Apache-2.0
"""Regenerate a suite's skill folder from LANDED canon — the Eurotas generator.

Canon governs: this script reads every component's living edition from the deployment's git repo
(never from drafts) and writes the folder the suite's manifest describes. The sources carry their
final shape — a canon entry says "read `reconcile.md` in this folder" because the manifest defines
the packaging — so the generator only packages: the Tier-1 description from the manifest into the
frontmatter, the skill body, and each reference file from its source's first heading on.

    python skills/gen_suite.py <river> <path-to-bare-repo> [out-dir] [--ref <ref>]

Rivers are declared in RIVERS below (Eurotas is the sixth; Aous keeps its own generator,
skills/gen_aous.py, because its packaging rewrote the road's index and appended layers). `--ref`
previews the encoding a branch or a staged proposal would produce, before it lands.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stasima.entries import parse_entry   # noqa: E402  (the envelope reader — supersession lives there)

RIVERS = {
    "eurotas": {
        "manifest": "meta/suites/eurotas.md",
        "skill": "technical/suites/eurotas/skill.md",
        "files": ["reconcile", "author", "message", "relay", "recover", "glossary"],
        "source_dir": "technical/suites/eurotas",
    },
}

REF = "refs/heads/main"


def blob(gd, path):
    r = subprocess.run(["git", "-C", gd, "cat-file", "blob", f"{REF}:{path}"], capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"cannot read {path} at {REF}: {r.stderr.decode().strip()}")
    return r.stdout.decode("utf-8")


def living(gd, path, hops=8):
    """Follow supersession from a component's home path to its living edition."""
    seen = []
    while hops:
        src = blob(gd, path)
        env, _ = parse_entry(src)
        nxt = env.get("superseded_by") or []
        if env.get("status") != "superseded" or not nxt:
            return path, src
        seen.append(path)
        path = nxt[0] if isinstance(nxt, list) else nxt
        hops -= 1
    raise SystemExit(f"supersession chain too long from {seen[0]}: {seen}")


def body_from_first_heading(src, what):
    """Everything from the source's first H1 on — the preamble above it addresses canon readers.
    A source with no H1 (the glossary) is packaged whole."""
    _, text = parse_entry(src)
    if text.startswith("# "):
        return text.rstrip() + "\n"
    at = text.find("\n# ")
    return (text if at < 0 else text[at + 1:]).rstrip() + "\n"


def provenance(river, home, path, manifest):
    edition = "" if path == home else f" — living edition {path}"
    preview = "" if REF == "refs/heads/main" else f" PREVIEW from {REF}, not yet landed."
    return (f"<!-- Encoding of canon {home}{edition} ({river.capitalize()} suite, manifest {manifest}). "
            f"Canon governs; this file is regenerated when canon changes.{preview} -->")


def description(gd, manifest_path):
    """The Tier-1 text: the LAST paragraph under the manifest's '## Skill description' heading
    (the paragraphs before it may explain the section to canon readers)."""
    _, src = living(gd, manifest_path)
    _, text = parse_entry(src)
    m = re.search(r"^## Skill description\s*\n(.*?)(?=^## )", text, re.S | re.M)
    if not m:
        raise SystemExit(f"{manifest_path}: no '## Skill description' section")
    paras = [p.strip() for p in re.split(r"\n\s*\n", m.group(1)) if p.strip()]
    if not paras:
        raise SystemExit(f"{manifest_path}: empty skill description")
    desc = " ".join(paras[-1].split())
    if len(desc) > 1024:
        raise SystemExit(f"skill description is {len(desc)} chars; the platform limit is 1024")
    return desc


def main():
    global REF
    args = sys.argv[1:]
    if "--ref" in args:
        i = args.index("--ref")
        REF = args[i + 1]
        del args[i:i + 2]
    if len(args) < 2 or args[0] not in RIVERS:
        raise SystemExit(f"usage: gen_suite.py <{'|'.join(RIVERS)}> <bare-repo> [out-dir] [--ref <ref>]")
    river, gd = args[0], args[1]
    spec = RIVERS[river]
    out = args[2] if len(args) > 2 else os.path.join(os.path.dirname(__file__), river)
    os.makedirs(out, exist_ok=True)

    desc = description(gd, spec["manifest"])
    path, src = living(gd, spec["skill"])
    skill = ("---\nname: " + river + "\ndescription: " + desc + "\n---\n\n"
             + provenance(river, spec["skill"], path, spec["manifest"]) + "\n\n"
             + body_from_first_heading(src, "skill"))
    with open(os.path.join(out, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(skill)
    for slug in spec["files"]:
        home = f"{spec['source_dir']}/{slug}.md"
        path, src = living(gd, home)
        text = provenance(river, home, path, spec["manifest"]) + "\n\n" + body_from_first_heading(src, slug)
        with open(os.path.join(out, f"{slug}.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print(f"wrote {out}: SKILL.md + {len(spec['files'])} files from {REF}")


if __name__ == "__main__":
    main()
