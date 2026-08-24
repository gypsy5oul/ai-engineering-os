#!/usr/bin/env python3
"""Ask the repository what order its work has to happen in.

policies/coupling-policy.json says file disjointness is necessary and not
sufficient, and then implements only the sufficient half: named surfaces two
roles must not both edit. This is the necessary half. Two tasks editing one file,
or one editing a module the other imports, are ordered whether or not anybody
named a surface for it -- and the repository already knows, so asking a proposer
to remember is asking for an ordering that sounds right.

Three signals, and the difference between them is how much they are worth:

  CS-01  path overlap   Certain. Two tasks name the same file.
  CS-02  import edge    Likely. One task's file imports another task's file.
  CS-03  co-change      Evidence. This repository's own history moves the files
                        together, which catches coupling through configuration,
                        a queue name or a column that no scan can see -- and
                        says nothing about which must land first, so it is
                        reported and never added.

Every added edge carries its evidence. An inference that cannot be argued with
just slows the graph down for reasons nobody can find.

    infer_dependencies.py --project . --item ACME-FEAT-001
    infer_dependencies.py --project . --item ACME-FEAT-001 --record
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import workitem as W  # noqa: E402

SKIP_DIRS = {".git", "node_modules", "vendor", "__pycache__", "dist", "build", ".venv"}


def policy(project=None):
    """The signal definitions, with the project's own import patterns merged in.

    A project knows its languages and its layout better than this file does, and
    the alternative to letting it say so is editing the script."""
    with open(os.path.join(ROOT, "policies", "code-signals.json"), encoding="utf-8") as fh:
        pol = json.load(fh)
    if project:
        try:
            with open(os.path.join(project, ".ai-engineering", "code-signals.json"),
                      encoding="utf-8") as fh:
                over = json.load(fh)
            for ext, pats in (over.get("import_patterns") or {}).items():
                pol["import_patterns"]["by_extension"].setdefault(ext, [])
                pol["import_patterns"]["by_extension"][ext] += list(pats)
            if over.get("co_change"):
                pol["co_change"].update(over["co_change"])
        except Exception:
            pass
    return pol


# --------------------------------------------------------------------------
# Which files each task owns
# --------------------------------------------------------------------------

def repo_files(project):
    """Every tracked-looking file, once. git if it is a repository, walk if not."""
    try:
        out = subprocess.run(["git", "-C", project, "ls-files"],
                             capture_output=True, text=True, timeout=60)
        if out.returncode == 0 and out.stdout.strip():
            return sorted(out.stdout.splitlines())
    except Exception:
        pass
    found = []
    for dirpath, dirnames, files in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in files:
            rel = os.path.relpath(os.path.join(dirpath, name), project).replace("\\", "/")
            found.append(rel)
    return sorted(found)


def expand(patterns, files):
    """The files a task's declared globs actually match.

    A glob matching nothing is reported by the caller rather than treated as an
    empty claim: a task that thinks it owns `src/payments/**` and owns nothing has
    either the wrong path or the wrong idea of the repository."""
    hit = set()
    for pat in patterns or []:
        p = pat.strip().lstrip("./")
        for f in files:
            if f == p or fnmatch.fnmatch(f, p) or f.startswith(p.rstrip("/*") + "/"):
                hit.add(f)
    return hit


def ownership(graph, files):
    """(task id -> owned files), and the globs that matched nothing."""
    owned, empty = {}, {}
    for t in graph.get("tasks", []):
        if t.get("state") in ("accepted", "abandoned"):
            continue
        pats = t.get("owns_paths")
        if not pats:
            continue
        got = expand(pats, files)
        owned[t["id"]] = got
        missed = [p for p in pats if not expand([p], files)]
        if missed:
            empty[t["id"]] = missed
    return owned, empty


# --------------------------------------------------------------------------
# CS-02: imports
# --------------------------------------------------------------------------

def import_targets(project, path, pol):
    """The module strings a file imports, or None when nothing here can read it."""
    ext = os.path.splitext(path)[1].lower()
    patterns = (pol["import_patterns"]["by_extension"] or {}).get(ext)
    if patterns is None:
        return None
    if not patterns:
        return set()
    try:
        with open(os.path.join(project, path), encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except Exception:
        return set()
    out = set()
    for pat in patterns:
        try:
            rx = re.compile(pat, re.M)
        except re.error:
            continue
        for m in rx.finditer(text):
            if m.groups():
                out.add(m.group(1))
    return out


def resolves_to(target, path, known_extensions=()):
    """Whether an import string plausibly names this file.

    Deliberately shallow: module resolution is a language's own problem, with
    search paths, aliases and index files. This compares the tail of the import
    against the file's own path, which is right often enough to be useful and
    wrong in ways the evidence line makes visible."""
    stem = re.sub(r"\.[^./]+$", "", path)
    # An import may name the file with its extension -- ESM requires `./b.js` --
    # so a trailing extension is stripped. Only a *known* one: `.model` in
    # `src.payments.model` is a module segment, and treating it as an extension
    # turned every Python dotted import into a reference to its own parent
    # package.
    target = target.strip()
    for ext in known_extensions:
        if ext and target.lower().endswith(ext):
            target = target[: -len(ext)]
            break
    parts = [p for p in re.split(r"[./\\:]+", target) if p and p not in (".", "..")]
    if not parts:
        return False
    tail = parts[-1]
    segments = stem.split("/")
    if tail not in segments:
        return False
    if len(parts) == 1:
        # A bare name matches only the file's own basename, not any directory on
        # the way to it: `import json` must not claim src/json/handler.py.
        return segments[-1] == tail or (segments[-1] == "index" and segments[-2:-1] == [tail])
    return "/".join(parts[-2:]) in stem or (parts[-2] in segments and tail in segments)


# --------------------------------------------------------------------------
# CS-03: what the history says
# --------------------------------------------------------------------------

def co_change(project, pol):
    """Pairs of files this repository changes together, above the threshold."""
    cfg = pol["co_change"]
    try:
        out = subprocess.run(
            ["git", "-C", project, "log", "--format=%H", "--name-only",
             "-n", str(cfg["window_commits"])],
            capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            return {}, "not a git repository, so there is no history to read"
    except Exception as exc:
        return {}, "git is unavailable: %r" % exc

    commits, current = [], []
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        if re.fullmatch(r"[0-9a-f]{40}", line.strip()):
            if current:
                commits.append(current)
            current = []
        else:
            current.append(line.strip())
    if current:
        commits.append(current)

    touched = Counter()
    together = Counter()
    for files in commits:
        uniq = sorted(set(files))
        # A sweeping commit says nothing about coupling: everything moved with
        # everything, which is a release, not a relationship.
        if len(uniq) > 40:
            continue
        for f in uniq:
            touched[f] += 1
        for i, a in enumerate(uniq):
            for b in uniq[i + 1:]:
                together[(a, b)] += 1

    pairs = {}
    for (a, b), n in together.items():
        if n < cfg["min_shared_commits"]:
            continue
        base = min(touched[a], touched[b]) or 1
        if n / float(base) >= cfg["min_ratio"]:
            pairs[(a, b)] = (n, base)
    return pairs, None


# --------------------------------------------------------------------------
# Putting it together
# --------------------------------------------------------------------------

def would_cycle(graph, dependent, dependency):
    """Whether making `dependent` wait for `dependency` closes a loop."""
    edges = defaultdict(set)
    for t in graph.get("tasks", []):
        edges[t["id"]] |= set(t.get("depends_on") or [])
    edges[dependent].add(dependency)
    seen, stack = set(), [dependency]
    while stack:
        node = stack.pop()
        if node == dependent:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(edges.get(node, ()))
    return False


def infer(project, graph, pol):
    """(edges, notes). An edge is (dependent, dependency, signal, evidence)."""
    files = repo_files(project)
    owned, empty_globs = ownership(graph, files)
    notes = []
    if not owned:
        return [], ["no task declares owns_paths, so there is nothing to infer from. A task that "
                    "says which files it will edit can be ordered against one that says the same; "
                    "one that does not cannot."]
    for tid, missed in sorted(empty_globs.items()):
        notes.append("%s claims %s, which matches no file in the repository"
                     % (tid, ", ".join(missed)))

    order = [t["id"] for t in graph["tasks"] if t["id"] in owned]
    edges = []

    # CS-01: the same file in two tasks. Certain, and not an inference.
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            shared = owned[a] & owned[b]
            if shared:
                edges.append((b, a, "path_overlap",
                              "both edit %s%s" % (", ".join(sorted(shared)[:3]),
                                                  " and %d more" % (len(shared) - 3)
                                                  if len(shared) > 3 else "")))

    # CS-02: one task's file imports another's.
    unreadable = set()
    known_ext = tuple(sorted((pol["import_patterns"]["by_extension"] or {}), key=len, reverse=True))
    for importer_task in order:
        for path in sorted(owned[importer_task]):
            targets = import_targets(project, path, pol)
            if targets is None:
                unreadable.add(os.path.splitext(path)[1].lower() or "(no extension)")
                continue
            for target in targets:
                for owner_task in order:
                    if owner_task == importer_task:
                        continue
                    for candidate in owned[owner_task]:
                        if candidate in owned[importer_task]:
                            continue
                        if resolves_to(target, candidate, known_ext):
                            edges.append((importer_task, owner_task, "import_edge",
                                          "%s imports %r, which is %s"
                                          % (path, target, candidate)))
                            break
    if unreadable:
        notes.append("no import pattern for %s, so files of that kind were not scanned. Add one "
                     "under import_patterns in .ai-engineering/code-signals.json."
                     % ", ".join(sorted(unreadable)))

    # De-duplicate, preferring the stronger signal for the same pair.
    best = {}
    rank = {"path_overlap": 0, "import_edge": 1}
    for dependent, dependency, signal, why in edges:
        key = (dependent, dependency)
        if key not in best or rank[signal] < rank[best[key][2]]:
            best[key] = (dependent, dependency, signal, why)

    # Two tasks that each import the other cannot be ordered. Adding whichever
    # edge came up first would pick a direction on iteration order, which is a
    # decision made by nobody and visible to no one. Both are dropped and said
    # out loud: the two tasks are one piece of work, or the modules should not
    # depend on each other.
    mutual = {(a, b) for (a, b) in best if (b, a) in best}
    for a, b in sorted({tuple(sorted(pair)) for pair in mutual}):
        notes.append("%s and %s each import the other (%s / %s). Neither edge was inferred: "
                     "there is no order between them. Either they are one task, or the cycle in "
                     "the code is the thing to fix."
                     % (a, b, best[(a, b)][3], best[(b, a)][3]))
    for pair in mutual:
        best.pop(pair, None)
    return sorted(best.values()), notes


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".")
    ap.add_argument("--item", required=True)
    ap.add_argument("--record", action="store_true",
                    help="add the certain and likely edges to the graph, with their evidence")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    graph = W.load_graph(project, args.item)
    if graph is None:
        print("ERROR %s has no graph" % args.item)
        return 2
    pol = policy(project)

    edges, notes = infer(project, graph, pol)
    pairs, why_not = co_change(project, pol)

    # CS-03 is reported against the tasks that own the files, never added.
    files = repo_files(project)
    owned, _ = ownership(graph, files)
    hints = []
    for (a, b), (n, base) in sorted(pairs.items()):
        ta = [t for t, fs in owned.items() if a in fs]
        tb = [t for t, fs in owned.items() if b in fs]
        for x in ta:
            for y in tb:
                if x != y and not any(e[0] == y and e[1] == x for e in edges) \
                        and not any(e[0] == x and e[1] == y for e in edges):
                    hints.append((x, y, "%s and %s changed together in %d of %d commits"
                                  % (a, b, n, base)))

    if args.json:
        print(json.dumps({
            "edges": [{"dependent": d, "dependency": p, "signal": s, "evidence": w}
                      for d, p, s, w in edges],
            "co_change": [{"tasks": [x, y], "evidence": w} for x, y, w in hints],
            "notes": notes, "history": why_not,
            "cannot_see": pol["cannot_see"]}, indent=2))
        return 0

    if not edges and not hints:
        print("%s: nothing to infer." % args.item)
        for n in notes:
            print("  note: %s" % n)
        return 0

    if edges:
        print("Ordering the repository implies:")
        for dependent, dependency, signal, why in edges:
            print("  %-7s waits for %-7s  %-13s %s" % (dependent, dependency, signal, why))
    if hints:
        print("\nHistory suggests, without saying which order (CS-03, never added):")
        for x, y, why in hints:
            print("  %-7s and %-7s  %s" % (x, y, why))
    for n in notes:
        print("\nnote: %s" % n)
    if why_not:
        print("\nnote: %s" % why_not)

    if not args.record:
        print("\nNothing was written. Re-run with --record to add the ordering above.")
        return 0

    added, refused = [], []
    for dependent, dependency, signal, why in edges:
        t = W.task(graph, dependent)
        if dependency in (t.get("depends_on") or []):
            continue
        if would_cycle(graph, dependent, dependency):
            refused.append((dependent, dependency, why))
            continue
        t["depends_on"] = sorted(set(t.get("depends_on") or []) | {dependency})
        t.setdefault("derived_depends_on", []).append(
            {"task": dependency, "signal": signal, "evidence": why, "at": W.now()})
        added.append((dependent, dependency, signal, why))

    if refused:
        print("\nREFUSED, and nothing was written for these:")
        for dependent, dependency, why in refused:
            print("  %s waiting for %s would make the graph cyclic (%s)"
                  % (dependent, dependency, why))
        print("A cycle means the split was wrong. Fix the decomposition rather than dropping "
              "one of the two edges.")
        if not added:
            return 1

    if added:
        W.save_graph(project, graph)
        W.record(project, args.item, "dependencies_inferred",
                 added=[{"dependent": d, "dependency": p, "signal": s, "evidence": w}
                        for d, p, s, w in added],
                 refused=[{"dependent": d, "dependency": p} for d, p, _ in refused])
        print("\n%d edge(s) added." % len(added))
    else:
        print("\nNothing to add; the graph already says all of this.")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
