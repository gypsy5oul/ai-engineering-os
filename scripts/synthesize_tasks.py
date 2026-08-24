#!/usr/bin/env python3
"""Turn one stage task into the several tasks it actually is.

A stage is a unit of accountability, not a unit of work. `DEV` for a payments
change is one node in the graph and five people's work in reality, and a graph
that cannot say so cannot schedule it, parallelise it, or show anyone where the
change has got to.

Two modes, and the difference between them is what is being invented:

  --derive   Split by the artifacts the stage produces and the roles that own
             them, read from policies/artifact-model.json. Invents nothing. If
             one role owns everything the stage produces, there is nothing to
             derive and this refuses rather than guessing a split.

  --from     Take a decomposition an agent proposed, validate every rule in
             policies/task-synthesis.json, and graft what survives.

The judgement stays with the agent; the rules, the graph and the refusal stay
here. That is the same split as everywhere else in this repository, and the
reason there is no heuristic in this file pretending to be an engineer.

    synthesize_tasks.py --project . --item ACME-FEAT-001 --task T-009 --derive
    synthesize_tasks.py --project . --item ACME-FEAT-001 --from proposal.json
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import workitem as W  # noqa: E402
import check_dod  # noqa: E402
import jsonschema_mini as J  # noqa: E402

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def policy():
    with open(os.path.join(ROOT, "policies", "task-synthesis.json"), encoding="utf-8") as fh:
        return json.load(fh)


def registry():
    with open(os.path.join(ROOT, "policies", "agent-registry.json"), encoding="utf-8") as fh:
        return json.load(fh)


def artifact_types():
    types = check_dod.model()["artifact_types"]
    return {a["code"]: a for a in types} if isinstance(types, list) else types


def owner_of(code):
    return (artifact_types().get(code) or {}).get("owner_role")


# --------------------------------------------------------------------------
# Validation. Every rule here is one entry in policies/task-synthesis.json.
# --------------------------------------------------------------------------

def check(proposal, graph, project):
    """Returns (errors, parent). An empty error list is the only way in."""
    pol = policy()
    errors = []
    parent = W.task(graph, proposal["parent"])
    if parent is None:
        return ["no task %s in this graph" % proposal["parent"]], None
    if parent.get("parent"):
        errors.append("TS-06: %s is already a child. One level of decomposition, because a "
                      "stage that needs more is a work item that was scoped wrong."
                      % parent["id"])
    if parent.get("synthesis"):
        errors.append("TS-06: %s has already been decomposed into %s"
                      % (parent["id"], ", ".join(parent["synthesis"].get("children", []))))
    if parent.get("state") not in ("queued", "assigned"):
        errors.append("TS-07: %s is %s. A stage is decomposed before it is worked, not after."
                      % (parent["id"], parent.get("state")))

    children = proposal["children"]
    limit = pol["max_children"]
    if not 2 <= len(children) <= limit:
        errors.append("TS-06: %d children; the bound is 2 to %d" % (len(children), limit))

    keys = [c["key"] for c in children]
    if len(set(keys)) != len(keys):
        errors.append("TS-04: sibling keys must be unique: %s" % ", ".join(sorted(keys)))

    # TS-01: the children owe exactly what the stage owed.
    owed = set(parent.get("produces") or [])
    given = set()
    for c in children:
        given |= set(c.get("produces") or [])
    if owed - given:
        errors.append("TS-01: nothing produces %s, which %s owes. A decomposition that drops an "
                      "artifact turns a stage the organization owes into one nobody owes, and "
                      "the parent's definition of done still passes."
                      % (", ".join(sorted(owed - given)), parent["id"]))
    if given - owed:
        errors.append("TS-01: %s produces %s, which %s does not owe. Producing an artifact "
                      "outside the stage puts it outside the stage's gate as well."
                      % (parent["id"], ", ".join(sorted(given - owed)), parent["id"]))

    known = {a["name"] for a in registry()["agents"]}
    scope = check_dod.load_json_policy("write-scope.json") if hasattr(
        check_dod, "load_json_policy") else None
    predicates = check_dod.model()["dod_predicates"]
    types = artifact_types()

    for c in children:
        where = "child %r" % c["key"]
        # TS-02
        if c["role"] not in known:
            errors.append("TS-02: %s names role %r, which is not in the agent registry"
                          % (where, c["role"]))
        else:
            for code in c.get("produces") or []:
                if code not in types:
                    errors.append("TS-02: %s produces %r, which is not an artifact type"
                                  % (where, code))
                    continue
                why = cannot_write(c["role"], types[code].get("storage", ""))
                if why:
                    errors.append("TS-02: %s assigns %s to %s, which cannot write %s -- %s"
                                  % (where, code, c["role"], types[code].get("storage"), why))
        # TS-03
        want = c.get("risk")
        if want and RISK_ORDER.get(want, 1) < RISK_ORDER.get(parent.get("risk", "MEDIUM"), 1):
            errors.append("TS-03: %s lowers risk from %s to %s. Decomposing high-risk work into "
                          "low-risk pieces routes around the model floor, the approval gates and "
                          "the concurrency limits one level down."
                          % (where, parent.get("risk"), want))
        # TS-04
        for dep in c.get("depends_on") or []:
            if dep not in keys:
                errors.append("TS-04: %s depends on %r, which is not a sibling. The parent "
                              "already carries this change's outside dependencies."
                              % (where, dep))
        # TS-05
        for entry in c.get("definition_of_done") or []:
            fn, args = check_dod.parse_predicate(entry)
            if fn is None:
                errors.append("TS-05: %s has %r, which is not a predicate call" % (where, entry))
            elif fn not in predicates:
                errors.append("TS-05: %s calls %r, which is not a predicate. An unknown "
                              "predicate is skipped by the evaluator, so it is a definition of "
                              "done that always passes." % (where, fn))
            else:
                wanted = len(predicates[fn].get("args") or [])
                if len(args) != wanted:
                    errors.append("TS-05: %s calls %s with %d argument(s); it takes %d"
                                  % (where, fn, len(args), wanted))

    # TS-08: a shared contract keeps exactly one owner across the split.
    surface = parent.get("coupled_surface")
    if surface:
        owners = [c["key"] for c in children
                  if c.get("coupled_surface") == surface
                  or surface in (c.get("produces") or [])]
        if not owners:
            errors.append("TS-08: %s owns the %s surface and no child claims it. The coupling "
                          "policy gives each shared contract one owner, and dropping that at the "
                          "moment the work becomes parallel is when it starts to matter. Set "
                          "\"coupled_surface\": \"%s\" on whichever child edits it."
                          % (parent["id"], surface, surface))
        elif len(owners) > 1:
            errors.append("TS-08: %s children claim the %s surface (%s). One owner, or they "
                          "cannot run at the same time and the split has serialised itself away."
                          % (len(owners), surface, ", ".join(owners)))

    errors.extend(cycles(children))
    return errors, parent


def cycles(children):
    """TS-04: the sibling graph must be acyclic."""
    edges = {c["key"]: [d for d in (c.get("depends_on") or [])] for c in children}
    state = {}

    def walk(node, trail):
        if state.get(node) == "done":
            return []
        if state.get(node) == "open":
            return ["TS-04: the children depend on each other in a cycle: %s"
                    % " -> ".join(trail + [node])]
        state[node] = "open"
        found = []
        for nxt in edges.get(node, []):
            if nxt in edges:
                found += walk(nxt, trail + [node])
        state[node] = "done"
        return found

    out = []
    for key in edges:
        out += walk(key, [])
    return sorted(set(out))


def cannot_write(role, storage):
    """Why this role could not write there, or None. The same question the
    artifact model is held to, asked of a proposed task."""
    if not storage or not storage.startswith(("docs/", "tests/", "ops/", "src/")):
        return None
    with open(os.path.join(ROOT, "policies", "tool-permissions.json"), encoding="utf-8") as fh:
        profiles = json.load(fh)["profiles"]
    with open(os.path.join(ROOT, "policies", "write-scope.json"), encoding="utf-8") as fh:
        scope = json.load(fh)
    entry = next((a for a in registry()["agents"] if a["name"] == role), None)
    if entry is None:
        return "it is not a known agent"
    tools = (profiles.get(entry.get("tool_profile")) or {}).get("tools") or []
    if not any(t in tools for t in ("Write", "Edit", "NotebookEdit")):
        return "its tool profile %r holds no write tool" % entry.get("tool_profile")
    role_scope = (scope.get("roles") or {}).get(role)
    if role_scope is None:
        return None
    where = storage.rstrip("/")
    if role_scope.get("mode") == "allow":
        if not any(where.startswith(p.replace("/**", "").rstrip("/"))
                   for p in role_scope.get("allow", [])):
            return "its allow-mode scope does not cover that path"
    elif role_scope.get("mode") == "deny":
        if any(where.startswith(p.replace("/**", "").rstrip("/"))
               for p in role_scope.get("deny", [])):
            return "its deny list covers that path"
    return None


# --------------------------------------------------------------------------
# Derived mode: reading, not guessing
# --------------------------------------------------------------------------

def derive(parent):
    """One child per role that owns some of what this stage produces.

    Everything here is already written down in the artifact model. A stage owing
    an ARCH and an SLO owes them to two different owners, and saying so is
    reading rather than inventing. When one role owns all of it there is nothing
    to read, and this returns nothing rather than a split it made up.
    """
    by_role = {}
    for code in parent.get("produces") or []:
        owner = owner_of(code)
        if not owner:
            return [], "artifact %s has no owner_role in the model" % code
        by_role.setdefault(owner, []).append(code)
    if len(by_role) < 2:
        return [], ("everything %s produces is owned by one role, so there is no split to "
                    "derive. Propose one with --from if the stage still needs decomposing."
                    % parent["id"])
    surface = parent.get("coupled_surface")
    if surface and surface not in (parent.get("produces") or []):
        return [], ("%s owns the %s surface, and which piece of the work edits it is a judgement "
                    "the artifact model does not contain. Propose the split with --from and name "
                    "the owner." % (parent["id"], surface))
    children = []
    for role, codes in sorted(by_role.items()):
        children.append({
            "key": role,
            "title": "%s: %s" % (parent.get("title", parent["id"]), ", ".join(sorted(codes))),
            "role": role,
            "produces": sorted(codes),
            "definition_of_done": ["artifact_exists(%s)" % c for c in sorted(codes)],
        })
    return children, None


def report(errors, parent_id):
    print("REFUSED: the decomposition of %s does not satisfy policies/task-synthesis.json."
          % parent_id)
    for e in errors:
        print("  - %s" % e)
    print("\nNothing was written. Fix the proposal and run it again.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".")
    ap.add_argument("--item", required=True)
    ap.add_argument("--task", help="the stage task to decompose (required with --derive)")
    ap.add_argument("--derive", action="store_true",
                    help="split by artifact ownership, inventing nothing")
    ap.add_argument("--from", dest="source",
                    help="a proposal file, or - for stdin")
    ap.add_argument("--proposed-by", help="the agent that produced the proposal")
    ap.add_argument("--dry-run", action="store_true", help="validate and print, write nothing")
    ap.add_argument("--no-infer", action="store_true",
                    help="do not ask the repository about the ordering of the new tasks")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    graph = W.load_graph(project, args.item)
    if graph is None:
        print("ERROR %s has no graph" % args.item)
        return 2

    if args.derive:
        if not args.task:
            print("ERROR --derive needs --task")
            return 2
        parent = W.task(graph, args.task)
        if parent is None:
            print("ERROR no task %s" % args.task)
            return 2
        children, why = derive(parent)
        if not children:
            print("REFUSED: %s" % why)
            return 1
        proposal = {"parent": args.task, "children": children,
                    "rationale": "derived from artifact ownership in the model"}
        mode = "derived"
    elif args.source:
        raw = sys.stdin.read() if args.source == "-" else open(args.source, encoding="utf-8").read()
        try:
            proposal = json.loads(raw)
        except ValueError as exc:
            print("REFUSED: the proposal is not JSON: %s" % exc)
            return 1
        with open(os.path.join(ROOT, "schemas", "task-proposal.schema.json"),
                  encoding="utf-8") as fh:
            try:
                J.validate(proposal, json.load(fh))
            except Exception as exc:
                print("REFUSED: the proposal does not match schemas/task-proposal.schema.json")
                print("  - %s" % exc)
                return 1
        mode = "proposed"
    else:
        print("ERROR give --derive or --from")
        return 2

    errors, parent = check(proposal, graph, project)
    if errors:
        report(errors, proposal["parent"])
        return 1

    if args.dry_run:
        print("%s would become %d task(s):" % (parent["id"], len(proposal["children"])))
        for c in proposal["children"]:
            print("  %-14s %-24s %s" % (c["key"], c["role"],
                                        ", ".join(c.get("produces") or []) or "-"))
        print("\n%s keeps its definition of done and waits for all of them." % parent["id"])
        return 0

    made = W.graft(graph, proposal["parent"], proposal["children"], mode=mode,
                   rationale=proposal.get("rationale"), proposed_by=args.proposed_by)
    W.save_graph(project, graph)
    W.record(project, args.item, "synthesized", task=parent["id"], mode=mode,
             children=[t["id"] for t in made], rationale=proposal.get("rationale"),
             proposed_by=args.proposed_by)
    print("%s decomposed into %d task(s):" % (parent["id"], len(made)))
    for t in made:
        print("  %-7s %-24s %-22s %s" % (t["id"], t["role"], t["title"][:22],
                                         ", ".join(t.get("produces") or []) or "-"))
    print("\n%s now waits for all of them and keeps the stage's definition of done."
          % parent["id"])

    if args.no_infer:
        print("\nDependency inference skipped. Run infer_dependencies.py before the children "
              "are claimed, or two of them may edit one file at the same time.")
        return 0
    return infer_after_graft(project, args.item, [t["id"] for t in made])


def infer_after_graft(project, item, children):
    """Ask the repository about the ordering of the tasks just created.

    Part of the pipeline rather than a separate command anyone has to remember.
    A decomposition is exactly the moment new ordering appears -- several tasks
    that did not exist a second ago, some of them editing the same files -- and a
    tool that has to be invoked by hand at precisely that moment will be missed.
    """
    import subprocess
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "infer_dependencies.py"),
         "--project", project, "--item", item, "--record"],
        capture_output=True, text=True, timeout=300)
    body = (proc.stdout or "").strip()
    if not body:
        return 0
    print("\n--- ordering implied by the repository " + "-" * 34)
    print(body)
    if proc.returncode != 0:
        # An inference that refused something is not a failed decomposition: the
        # children exist and are correct. It is a cycle in the code, and the exit
        # code says so without pretending the graft did not happen.
        print("\nThe decomposition stands; the ordering above did not. Fix the cycle, then "
              "re-run infer_dependencies.py --record.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
