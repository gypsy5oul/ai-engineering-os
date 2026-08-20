#!/usr/bin/env python3
"""Validate and inspect the Level 2 department execution cycles.

The macro workflows govern stage-to-stage progression. These govern task-to-task
delegation, review and rework inside a department. A state machine that has an
unreachable state, a dead end, or a review position filled by the worker is not a
control; it is a diagram.

  python3 scripts/check_cycle.py                    # validate every cycle
  python3 scripts/check_cycle.py --graph CYCLE-DEV  # print the state machine
  python3 scripts/check_cycle.py --trace CYCLE-DEV  # walk a happy path and a rework path
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from minyaml import parse_file  # noqa: E402
from jsonschema_mini import validate  # noqa: E402

START = "ASSIGNED"
errors, warnings = [], []


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def cycles():
    base = os.path.join(ROOT, "sdlc", "cycles")
    out = {}
    for name in sorted(os.listdir(base)):
        if name.endswith((".yaml", ".yml")):
            c = parse_file(os.path.join(base, name))
            out[c["id"]] = (name, c)
    return out


# ---------------------------------------------------------------- analysis

def reachable(states, transitions, start=START):
    seen, stack = {start}, [start]
    while stack:
        cur = stack.pop()
        for target in (transitions.get(cur) or {}).values():
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


def check_machine(cid, c):
    states = set(c["states"])
    trans = c["transitions"]
    generic = load("policies/department-cycle.json")
    terminal = set(generic["terminal_states"])

    if START not in states:
        errors.append("%s: no %s state" % (cid, START))
        return

    for src, edges in trans.items():
        if src not in states:
            errors.append("%s: transition from undeclared state %s" % (cid, src))
        for event, target in edges.items():
            if target not in states:
                errors.append("%s: %s --%s--> undeclared state %s" % (cid, src, event, target))

    seen = reachable(states, trans)
    unreachable = states - seen
    if unreachable:
        errors.append("%s: unreachable states %s. A state nothing can enter is not a control."
                      % (cid, sorted(unreachable)))

    for state in states:
        outgoing = trans.get(state) or {}
        if state in terminal:
            if outgoing:
                errors.append("%s: terminal state %s has outgoing transitions %s"
                              % (cid, state, sorted(outgoing)))
            continue
        if not outgoing:
            errors.append("%s: dead end at %s. Work that enters it can never leave."
                          % (cid, state))

    # Every non-terminal path must be able to reach a terminal state.
    for state in sorted(states - terminal):
        if not (reachable(states, trans, state) & terminal):
            errors.append("%s: %s cannot reach %s. Work entering it is stuck."
                          % (cid, state, sorted(terminal)))

    # ACCEPTED must be reachable only through a definition-of-done evaluation.
    # A head that could accept by assertion would make every predicate advisory.
    into_accepted = [(src, event) for src, edges in trans.items()
                     for event, target in edges.items() if target == "ACCEPTED"]
    if not into_accepted:
        errors.append("%s: nothing can reach ACCEPTED" % cid)
    for src, event in into_accepted:
        # The only way in. The withdrawn edge used to be exempted here, which meant
        # a cancelled item could satisfy a stage's definition of done with no
        # predicate evaluated at all. Withdrawal now has its own terminal state.
        if src == "ACCEPTANCE_REQUESTED" and event == "dod_pass":
            continue
        errors.append("%s: ACCEPTED is reachable from %s via '%s'. Acceptance is determined by the "
                      "definition of done, not asserted." % (cid, src, event))

    # The rework limit must be expressible as a transition. A limit the machine
    # cannot act on leaves an over-limit item with no legal move but to keep
    # cycling, which is how an honest counter becomes a trap.
    if (c.get("rework") or {}).get("limit") is not None:
        edges = trans.get("CHANGES_REQUESTED") or {}
        if not any(target == "ESCALATED" for target in edges.values()):
            errors.append("%s: rework declares a limit but CHANGES_REQUESTED has no edge to "
                          "ESCALATED, so reaching the limit has no legal move." % cid)
    if "ACCEPTANCE_REQUESTED" in states:
        edges = trans.get("ACCEPTANCE_REQUESTED") or {}
        if edges.get("dod_fail") is None:
            errors.append("%s: ACCEPTANCE_REQUESTED cannot fail. A check that can only pass is not "
                          "a check." % cid)

    # The rework loop must actually loop back to the worker.
    if "CHANGES_REQUESTED" in states:
        if (trans.get("CHANGES_REQUESTED") or {}).get("resume") != "IN_PROGRESS":
            errors.append("%s: CHANGES_REQUESTED does not return to IN_PROGRESS" % cid)
    for review in ("PEER_REVIEW", "LEAD_REVIEW"):
        if review in states and "CHANGES_REQUESTED" not in (trans.get(review) or {}).values():
            errors.append("%s: %s cannot request changes. A review that can only pass is not a review."
                          % (cid, review))


def _can_write_artifact(role, artifact_code):
    """Could this role write the storage location of that artifact type?"""
    model = load("policies/artifact-model.json")
    scope = load("policies/write-scope.json")
    spec = next((a for a in model["artifact_types"] if a["code"] == artifact_code), None)
    if spec is None:
        return False
    storage = spec.get("storage", "").rstrip("/")
    entry = scope.get("roles", {}).get(role)
    if entry is None:
        return True  # unscoped roles can write anywhere their tools allow
    if entry.get("mode") == "allow":
        return any(storage.startswith(p.replace("/**", "").rstrip("/"))
                   for p in entry.get("allow", []))
    return not any(storage.startswith(p.replace("/**", "").rstrip("/"))
                   for p in entry.get("deny", []))


def check_positions(cid, c, registry, profiles, human_roles):
    pos = c["positions"]
    agents = {a["name"]: a for a in registry["agents"]}
    lead, workers, peer = pos["lead"], pos["workers"], pos["peer_reviewer"]

    if lead not in agents:
        errors.append("%s: lead %r is not a registered agent" % (cid, lead))
    for w in workers:
        if w not in agents:
            errors.append("%s: worker %r is not a registered agent" % (cid, w))

    head = pos["head"]
    owner = pos["human_owner"]

    # The human owner governs; it never staffs an operational position.
    if owner["role"] in agents:
        errors.append("%s: human_owner %r is an agent" % (cid, owner["role"]))
    elif owner["role"].replace("-", "_") not in human_roles:
        errors.append("%s: human_owner %r is not one of the project's named human roles %s"
                      % (cid, owner["role"], sorted(human_roles)))
    if not owner.get("authority"):
        errors.append("%s: human_owner has no stated authority. A governance role that decides "
                      "nothing specific decides everything by default." % cid)
    for role_name in (lead, peer) + tuple(workers):
        if role_name == owner["role"]:
            errors.append("%s: human_owner also fills an operational position" % cid)

    if head["kind"] == "agent":
        entry = agents.get(head["role"])
        if entry is None:
            errors.append("%s: agent head %r is not a registered agent" % (cid, head["role"]))
        elif entry["tool_profile"] not in ("lead", "orchestrator"):
            errors.append("%s: agent head %r holds the %s profile; a head must be lead or "
                          "orchestrator" % (cid, head["role"], entry["tool_profile"]))
        if head["role"] in workers:
            errors.append("%s: head %r is also a worker in its own department"
                          % (cid, head["role"]))
        if head["role"] == peer:
            errors.append("%s: head %r is also the peer reviewer" % (cid, head["role"]))
        # The head must be able to bring in its own lead, or it cannot delegate.
        if entry and lead not in entry.get("may_spawn", []) and head["role"] != lead:
            errors.append("%s: head %r may not spawn its own lead %r; it cannot delegate"
                          % (cid, head["role"], lead))
    else:
        if not head.get("human_exception_reason"):
            errors.append("%s: head is human but gives no reason. Making the head a human puts a "
                          "person in every departmental rollup and defeats the autonomy target, so "
                          "an exception must be argued." % cid)
        if head["role"] in agents:
            errors.append("%s: head declared human but %r is an agent" % (cid, head["role"]))

    if head.get("receives", "rollup") != "rollup":
        errors.append("%s: the head receives %r rather than a rollup" % (cid, head.get("receives")))

    if peer == "mutual":
        if len(workers) < 2:
            errors.append("%s: peer_reviewer 'mutual' needs at least two workers; with one worker "
                          "there is no peer" % cid)
    else:
        if peer not in agents:
            errors.append("%s: peer_reviewer %r is not a registered agent" % (cid, peer))
        else:
            if peer in workers:
                errors.append("%s: peer_reviewer %r is also a worker. A worker reviewing its own "
                              "stream is not a review." % (cid, peer))
            tools = profiles["profiles"][agents[peer]["tool_profile"]]["tools"]
            if "Write" in tools or "Edit" in tools:
                # Holding write tools is not itself the problem. Being able to write
                # the artifact under review is: that is what makes a reviewer a
                # second author.
                if _can_write_artifact(peer, c["work_item"]["artifact"]):
                    errors.append("%s: peer_reviewer %r can write %s, the artifact it reviews. A "
                                  "reviewer that can edit becomes a second author."
                                  % (cid, peer, c["work_item"]["artifact"]))
                else:
                    warnings.append("%s: peer_reviewer %r holds write tools but cannot write %s, "
                                    "the artifact under review. Independence rests on the write "
                                    "scope rather than on the tool list."
                                    % (cid, peer, c["work_item"]["artifact"]))
        if lead in workers and peer == lead:
            errors.append("%s: lead, worker and peer reviewer are the same agent. The cycle has no "
                          "independent check at all." % cid)

    acc = c.get("acceptance", {})
    if acc.get("requested_by") == acc.get("determined_by"):
        errors.append("%s: the position that requests acceptance also determines it" % cid)
    if acc.get("determined_by") and "check_dod" not in acc["determined_by"]:
        errors.append("%s: acceptance is determined by %r rather than the definition-of-done "
                      "evaluator" % (cid, acc["determined_by"]))
    head_authority = c["positions"]["head"].get("authority") or []
    for item in head_authority:
        low = item.lower()
        if ("accept" in low or "declare" in low) and "request" not in low:
            errors.append("%s: head authority %r reads as deciding acceptance rather than "
                          "requesting it" % (cid, item))

    if c["rollup"]["produced_by"] != lead:
        errors.append("%s: the rollup must be produced by the lead, not %r"
                      % (cid, c["rollup"]["produced_by"]))
    order = c["escalation"]["order"]
    if order[0] != "worker" or order[-1] != "human_owner":
        errors.append("%s: escalation must run worker -> ... -> head -> human_owner, got %s"
                      % (cid, order))
    if "head" not in order:
        errors.append("%s: escalation reaches the human without passing the head" % cid)
    if "lead" not in order:
        errors.append("%s: escalation skips the lead. A problem reaching the head without the lead "
                      "knowing means the lead was not told about its own department." % cid)


def check_wiring(cycles_by_id):
    """Each cycle's used_by_stages must name real stages, and each stage that names
    a cycle must be named back. Two directions that can drift are one direction."""
    base = os.path.join(ROOT, "sdlc", "workflows")
    stage_cycle = {}
    completing = {}
    all_stages = set()
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        wf = parse_file(os.path.join(base, name))
        for s in wf["stages"]:
            key = "%s/%s" % (wf["id"], s["id"])
            all_stages.add(key)
            if s.get("department_cycle"):
                cid = s["department_cycle"]
                stage_cycle.setdefault(cid, []).append(key)
                role = s.get("cycle_role")
                if role not in ("enters", "continues", "completes"):
                    errors.append("%s: declares %s but no cycle_role. A stage early in a "
                                  "department's engagement cannot require the cycle to be accepted."
                                  % (key, cid))
                    continue
                dod = s.get("definition_of_done", [])
                required = ("cycle_accepted(%s)" % cid, "cycle_rollup_reported(%s)" % cid,
                            "no_open_rework(%s)" % cid)
                if role == "completes":
                    for pred in required:
                        if pred not in dod:
                            errors.append("%s: completes %s but its definition of done omits %s"
                                          % (key, cid, pred))
                else:
                    for pred in required:
                        if pred in dod:
                            errors.append("%s: has cycle_role '%s' but requires %s. The department's "
                                          "work has not concluded here." % (key, role, pred))
                completing.setdefault((wf["id"], cid), []).append((key, role))
    # Exactly one stage per workflow per cycle concludes it.
    for (wid, cid), entries in completing.items():
        finishers = [k for k, role in entries if role == "completes"]
        if len(finishers) == 0:
            errors.append("%s: %s is entered but never completed. Nothing would ever check that the "
                          "department finished." % (wid, cid))
        elif len(finishers) > 1:
            errors.append("%s: %s is completed at more than one stage: %s" % (wid, cid, finishers))

    for cid, (fname, c) in cycles_by_id.items():
        for ref in c["used_by_stages"]:
            if ref not in all_stages:
                errors.append("%s: used_by_stages names %r, which no workflow defines" % (cid, ref))
            elif ref not in stage_cycle.get(cid, []):
                errors.append("%s: claims stage %s, but that stage does not declare it" % (cid, ref))
    for cid, keys in stage_cycle.items():
        if cid not in cycles_by_id:
            errors.append("stages %s declare unknown cycle %s" % (keys, cid))
            continue
        for key in keys:
            if key not in cycles_by_id[cid][1]["used_by_stages"]:
                errors.append("%s declares %s, which does not list it in used_by_stages" % (key, cid))


# ---------------------------------------------------------------- output

def graph(cid, c):
    print("%s  %s\n" % (cid, c["name"]))
    print("  positions")
    pos = c["positions"]
    print("    human owner     %s (governance only)" % pos["human_owner"]["role"])
    for a in pos["human_owner"]["authority"]:
        print("                      · %s" % a)
    print("    head            %s (%s) receives the rollup"
          % (pos["head"].get("role", "-"), pos["head"]["kind"]))
    print("    lead            %s" % pos["lead"])
    print("    workers         %s" % ", ".join(pos["workers"]))
    print("    peer reviewer   %s" % pos["peer_reviewer"])
    if pos.get("specialist_reviewers"):
        print("    specialists     %s" % ", ".join(pos["specialist_reviewers"]))
    print("\n  state machine")
    for state in c["states"]:
        edges = c["transitions"].get(state) or {}
        if not edges:
            print("    %-22s (terminal)" % state)
            continue
        first = True
        for event, target in edges.items():
            print("    %-22s --%-20s--> %s" % (state if first else "", event, target))
            first = False
    if c.get("sub_cycles"):
        for sc in c["sub_cycles"]:
            print("\n  sub-cycle %s: %s" % (sc["id"], sc["name"]))
            print("    trigger: %s" % sc["trigger"])
            print("    owner:   %s" % sc["owner"])
            for q in sc["questions"]:
                print("      ? %s" % q)
            for k, v in sc["outcomes"].items():
                print("      %-22s %s" % (k, v))


def trace(cid, c):
    happy = [("ASSIGNED", "start"), ("IN_PROGRESS", "submit"), ("SELF_VALIDATION", "pass"),
             ("PEER_REVIEW", "pass"), ("LEAD_REVIEW", "pass"),
             ("READY_FOR_INTEGRATION", "set_complete"), ("ACCEPTANCE_REQUESTED", "dod_pass")]
    rework = [("ASSIGNED", "start"), ("IN_PROGRESS", "submit"), ("SELF_VALIDATION", "fail"),
              ("IN_PROGRESS", "submit"), ("SELF_VALIDATION", "pass"), ("PEER_REVIEW", "minor"),
              ("CHANGES_REQUESTED", "resume"), ("IN_PROGRESS", "submit"),
              ("SELF_VALIDATION", "pass"), ("PEER_REVIEW", "pass"), ("LEAD_REVIEW", "changes_required"),
              ("CHANGES_REQUESTED", "resume"), ("IN_PROGRESS", "submit"),
              ("SELF_VALIDATION", "pass"), ("PEER_REVIEW", "pass"), ("LEAD_REVIEW", "pass"),
              ("READY_FOR_INTEGRATION", "set_complete"), ("ACCEPTANCE_REQUESTED", "dod_pass")]
    for label, path in (("happy path", happy), ("rework path", rework)):
        print("\n  %s" % label)
        state = path[0][0]
        rounds = 0
        for expected, event in path:
            if state != expected:
                print("    BROKEN: expected %s, at %s" % (expected, state))
                return 1
            nxt = (c["transitions"].get(state) or {}).get(event)
            if nxt is None:
                print("    BROKEN: %s has no '%s' transition" % (state, event))
                return 1
            if nxt == "CHANGES_REQUESTED":
                rounds += 1
            print("    %-22s --%-18s--> %s" % (state, event, nxt))
            state = nxt
        print("    ends in %s after %d rework round(s), limit %d"
              % (state, rounds, c["rework"]["limit"]))
        if state == "ACCEPTED":
            print("    acceptance was REQUESTED by the head and DETERMINED by %s"
                  % c["acceptance"]["determined_by"])
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph")
    ap.add_argument("--trace")
    args = ap.parse_args()

    by_id = cycles()
    if args.graph:
        if args.graph not in by_id:
            print("unknown cycle. known: %s" % ", ".join(sorted(by_id)))
            return 2
        graph(args.graph, by_id[args.graph][1])
        return 0
    if args.trace:
        if args.trace not in by_id:
            print("unknown cycle. known: %s" % ", ".join(sorted(by_id)))
            return 2
        print("%s  %s" % (args.trace, by_id[args.trace][1]["name"]))
        return trace(args.trace, by_id[args.trace][1])

    schema = load("schemas/department-cycle.schema.json")
    registry = load("policies/agent-registry.json")
    profiles = load("policies/tool-permissions.json")
    human_roles = set(load("schemas/project-config.schema.json")
                      ["properties"]["approval"]["properties"])
    for cid, (fname, c) in by_id.items():
        for e in validate(c, schema):
            errors.append("sdlc/cycles/%s: %s" % (fname, e))
        check_machine(cid, c)
        check_positions(cid, c, registry, profiles, human_roles)
    check_wiring(by_id)

    for w in warnings:
        print("WARN  %s" % w)
    for e in errors:
        print("ERROR %s" % e)
    print("\n%d cycle(s), %d error(s), %d warning(s)" % (len(by_id), len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
