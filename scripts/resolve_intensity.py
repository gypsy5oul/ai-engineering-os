#!/usr/bin/env python3
"""How much organization a task gets, resolved from facts at plan time.

The department cycle is correct and it is not free. Worker, self-check, peer
review, lead review, rollup, acceptance is the right shape for a novel change to
a coupled surface, and it is what a one-line document correction currently gets
too, because the cycle has one path and every task walks all of it.

Intensity selects a path through the cycle that already exists. It does not
create four cycles, and it never removes a predicate: it decides who looks at the
work, never what the work has to satisfy.

Every signal can only **raise** the level. A model choosing how much review its
own work gets is the failure this would otherwise introduce; signals that can
only raise make the level an observation rather than an argument.

    resolve_intensity.py --project . --item ACME-FEAT-001 --all
    resolve_intensity.py --project . --item ACME-FEAT-001 --all --record
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import workitem as W  # noqa: E402

POLICY = os.path.join(ROOT, "policies", "workflow-intensity.json")


def policy():
    with open(POLICY, encoding="utf-8") as fh:
        return json.load(fh)


ORDER = ["MICRO", "STANDARD", "COMPLEX", "CRITICAL"]


def _rank(level):
    return ORDER.index(level) if level in ORDER else ORDER.index("STANDARD")


def _raise_to(current, floor, reason, reasons):
    """Take the higher of the two, and remember why only when it moved."""
    if _rank(floor) > _rank(current):
        reasons.append(reason)
        return floor
    return current


# Stages whose act cannot be undone by doing the opposite afterwards. Inferred
# from what the stage does rather than from what the change touches, which is a
# real limitation and is stated in the policy.
IRREVERSIBLE_STAGES = ("DEPLOY", "AUTHORIZE", "EXECUTE", "RELEASE", "PROMOTE", "ROLLBACK")
HEAVY_TYPES = ("incident", "release", "migration")
MAX_MICRO_PREDICATES = 6


def resolve(task, item=None, stage=None):
    """(level, why). The highest floor any signal set."""
    item = item or {}
    stage = stage or {}
    dod = task.get("definition_of_done") or []
    blob = " ".join(dod)
    reasons = []

    level = task.get("intensity")
    level = level.get("declared") if isinstance(level, dict) else level
    level = level or stage.get("intensity") or policy().get("default", "STANDARD")
    if level not in ORDER:
        level = "STANDARD"

    # IN-07 first, because it is the only mechanical one: a definition of done
    # that demands an independent verdict cannot be satisfied by a path where
    # nobody produces one. MICRO is not discouraged here, it is unreachable.
    if task.get("reviewer") or "agent_verdict" in blob:
        level = _raise_to(level, "STANDARD",
                          "IN-07 the definition of done needs an independent verdict, so a path "
                          "with no reviewer could not satisfy it", reasons)

    if "human_approval_recorded" in blob or stage.get("human_gate"):
        level = _raise_to(level, "COMPLEX",
                          "IN-08 a named human has to approve this, so it is not work the "
                          "organization was treating as trivial", reasons)

    if task.get("coupled_surface"):
        level = _raise_to(level, "COMPLEX",
                          "IN-05 this holds the %s coupled surface, and the review that matters "
                          "is the one that sees its consumers" % task["coupled_surface"], reasons)

    if (stage.get("complexity") or "") == "novel":
        level = _raise_to(level, "COMPLEX",
                          "IN-02 the stage is novel, which is where the lead's integration view "
                          "is worth most", reasons)

    if (item.get("type") or "") in HEAVY_TYPES:
        level = _raise_to(level, "COMPLEX",
                          "IN-04 a %s is paid for by somebody other than its author"
                          % item["type"], reasons)

    risk = str(task.get("risk") or stage.get("risk") or item.get("risk") or "MEDIUM").upper()
    if risk == "HIGH":
        level = _raise_to(level, "COMPLEX", "IN-01 HIGH risk", reasons)

    stage_id = (task.get("stage") or stage.get("id") or "").upper()
    if stage_id in IRREVERSIBLE_STAGES:
        level = _raise_to(level, "CRITICAL",
                          "IN-03 %s cannot be undone by doing the opposite afterwards, and "
                          "ceremony after the fact is not review" % stage_id, reasons)

    # Last, and unconditional. Anything that could lower it has already run.
    if risk == "CRITICAL":
        level = _raise_to(level, "CRITICAL",
                          "IN-01 CRITICAL risk, which no other signal may lower", reasons)

    # A ceiling rather than a floor: it cannot raise anything, it only refuses
    # MICRO. A wrong reading therefore costs ceremony, not review.
    if level == "MICRO" and len(dod) > MAX_MICRO_PREDICATES:
        level = "STANDARD"
        reasons.append("IN-06 %d predicates is not a MICRO task, by the predicate-count proxy"
                       % len(dod))

    # MICRO is reached by passing a test, not by being declared. Signals only
    # raise, so without this the level is unreachable in practice and the whole
    # policy is ceremony about ceremony -- the first run of this resolver put
    # every one of a feature's fifteen tasks at STANDARD or above, including a
    # two-predicate intake step with no reviewer, no gate and no artifact.
    #
    # It is still true that nothing risk-bearing can be lowered: the test is a
    # conjunction of negatives, so it can only apply to a task every raising
    # signal above stayed silent on.
    if not reasons and level == policy().get("default", "STANDARD"):
        small, why_not = qualifies_for_micro(task, item, stage)
        if small:
            return "MICRO", ("no signal raised this above the default and it passes the MICRO "
                             "test: %s" % why_not)
        reasons.append("stayed at %s: %s" % (level, why_not))

    if not reasons:
        reasons.append("no signal raised it above %s" % level)
    return level, "; ".join(reasons)


def qualifies_for_micro(task, item=None, stage=None):
    """(bool, why). Every condition is a negative, deliberately.

    A positive test for triviality would be a judgement. This is the absence of
    every reason the organization has to look at the work twice, which is
    something the graph can answer.
    """
    item, stage = item or {}, stage or {}
    dod = task.get("definition_of_done") or []
    blob = " ".join(dod)
    risk = str(task.get("risk") or stage.get("risk") or item.get("risk") or "MEDIUM").upper()
    complexity = task.get("complexity") or stage.get("complexity") or "routine"

    against = []
    if risk != "LOW":
        against.append("risk is %s" % risk)
    if complexity != "routine":
        against.append("the stage is %s" % complexity)
    if task.get("reviewer") or "agent_verdict" in blob:
        against.append("an independent verdict is required")
    if "human_approval_recorded" in blob or stage.get("human_gate"):
        against.append("a human approval is required")
    if task.get("coupled_surface"):
        against.append("it holds a coupled surface")
    if task.get("produces"):
        against.append("it produces %s, which another stage consumes"
                       % ", ".join(task["produces"]))
    if (item.get("type") or "") in HEAVY_TYPES:
        against.append("this is a %s" % item["type"])
    if len(dod) > MAX_MICRO_PREDICATES:
        against.append("%d predicates" % len(dod))
    if against:
        return False, "; ".join(against)
    return True, ("LOW risk, routine, no reviewer, no human gate, no coupled surface, "
                  "produces nothing another stage consumes, %d predicate(s)" % len(dod))


def path_for(level):
    return policy()["levels"][level]["path"]


def skips(level):
    return policy()["levels"][level].get("skips") or []


def record(task, item=None, stage=None):
    level, why = resolve(task, item, stage)
    declared = task.get("intensity")
    declared = declared.get("declared") if isinstance(declared, dict) else declared
    task["intensity"] = {"declared": declared or policy().get("default", "STANDARD"),
                         "resolved": level, "resolution_reason": why,
                         "resolved_at": W.now()}
    return level, why


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".")
    ap.add_argument("--item", required=True)
    ap.add_argument("--task")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record", action="store_true")
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    graph = W.load_graph(project, args.item)
    if graph is None:
        print("ERROR %s has no graph" % args.item)
        return 2
    item = W.load_item(project, args.item) or {}

    tasks = graph["tasks"] if args.all else [W.task(graph, args.task)]
    if tasks == [None]:
        print("ERROR no task %s" % args.task)
        return 2

    out = []
    for t in tasks:
        level, why = (record(t, item) if args.record else resolve(t, item))
        out.append({"task": t["id"], "role": t.get("role"), "stage": t.get("stage"),
                    "intensity": level, "skips": skips(level), "why": why})
    if args.record:
        W.save_graph(project, graph)

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print("%-7s %-11s %-10s %-24s %s"
              % ("TASK", "STAGE", "INTENSITY", "SKIPS", "WHY"))
        for r in out:
            print("%-7s %-11s %-10s %-24s %s"
                  % (r["task"], (r["stage"] or "")[:11], r["intensity"],
                     ", ".join(r["skips"]) or "-", r["why"][:58]))
        counts = {}
        for r in out:
            counts[r["intensity"]] = counts.get(r["intensity"], 0) + 1
        print("\n" + "  ".join("%s %d" % (k, counts.get(k, 0)) for k in ORDER))
    return 0


if __name__ == "__main__":
    sys.exit(main())
