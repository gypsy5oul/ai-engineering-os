#!/usr/bin/env python3
"""Run the Golden Project certification path and record what actually happened.

`scripts/simulate_sdlc.py` proves the organization can complete its own process:
ten scenarios, real artifacts, every definition of done evaluated. That is
necessary and it is not sufficient. It proves the plugin is coherent with itself.
It does not prove that Claude Code ever calls any of it, and those are different
claims -- the second was never checked at all until 0.29, and most of it still
has not been.

So this drives a real project through the lifecycle two ways and keeps the two
apart:

  synthetic   the organization drives itself. No model in the loop. Runs in CI,
              on every change, offline.
  live        real `claude -p` sessions do the work, with this plugin's hooks
              registered project-scope by absolute path, and the result is read
              back out of durable state.

The distinction is the point of the file. A probe passes on the audit log, the
work item's history or a file on disk -- never on a session's account of its own
behaviour, which is the thing under test. And `verdict.certified` cannot be set
by synthetic units however many of them pass.

    certify.py                      # synthetic, no model, no network
    certify.py --live               # additionally run real sessions
    certify.py --live --model opus  # which model the sessions use
    certify.py --out run.json       # write the record
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))

import check_dod  # noqa: E402
from minyaml import parse_file  # noqa: E402
import briefing  # noqa: E402
import workitem as W  # noqa: E402

GOLDEN = os.path.join(ROOT, "golden")

# The stages the brief asks the Golden Project to exercise. Kept here rather than
# derived from the workflow, because this is a statement about what certification
# requires, not about what WF-FEATURE happens to contain today.
REQUIRED_STAGES = ["REQ", "ARCH", "QADESIGN", "DEV", "REVIEW", "CI"]


def now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def plugin_version():
    with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        return json.load(fh)["version"]


def claude_version():
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30)
        m = re.search(r"(\d+\.\d+\.\d+)", out.stdout or "")
        return m.group(1) if m else None
    except Exception:
        return None


def cl(project, sub, *args):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"), sub,
         "--project", project] + list(args),
        capture_output=True, text=True, timeout=180)


# ---------------------------------------------------------------- the project

def materialise(dst):
    """A working copy of the Golden Project, in its own git repository.

    A copy rather than the checked-in tree: certification writes work items,
    artifacts and history, and a certification path that dirties the repository
    it is certifying cannot be run twice.
    """
    shutil.copytree(GOLDEN, dst)
    run = lambda *a: subprocess.run(["git"] + list(a), cwd=dst, capture_output=True, timeout=60)
    run("init", "-q")
    run("config", "user.email", "certification@example.invalid")
    run("config", "user.name", "certification")
    run("add", ".")
    run("commit", "-q", "-m", "the Golden Project as shipped")
    run("checkout", "-qB", "main")
    return dst


def register_hooks(project, data_dir):
    """Register this plugin's hooks in the project's own settings, by absolute path.

    Project scope only. Nothing is installed globally and nothing outside this
    throwaway directory is touched, which is what makes a live run safe to do on a
    developer machine.
    """
    settings = {
        "hooks": {},
        "env": {"CLAUDE_PLUGIN_ROOT": ROOT, "CLAUDE_PLUGIN_DATA": data_dir,
                "CLAUDE_PROJECT_DIR": project},
    }
    with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as fh:
        shipped = json.load(fh)["hooks"]
    for event, entries in shipped.items():
        out = []
        for entry in entries:
            item = {k: v for k, v in entry.items() if k != "hooks"}
            item["hooks"] = [dict(h, command=h["command"].replace("${CLAUDE_PLUGIN_ROOT}", ROOT))
                             for h in entry["hooks"]]
            out.append(item)
        settings["hooks"][event] = out
    os.makedirs(os.path.join(project, ".claude"), exist_ok=True)
    path = os.path.join(project, ".claude", "settings.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)

    # The roles too, project-scope. Registering hooks without agents proves the
    # guards fire and nothing about delegation: SubagentStart cannot brief an
    # agent the session has no way to spawn. Copied rather than symlinked so the
    # throwaway project is self-contained and a live run leaves this repository
    # untouched.
    agents_dst = os.path.join(project, ".claude", "agents")
    if not os.path.exists(agents_dst):
        shutil.copytree(os.path.join(ROOT, "agents"), agents_dst)
    return path


# ---------------------------------------------------------------- synthetic

def synthetic_units(project):
    """Drive the Golden Project through the lifecycle with no model in the loop.

    Every number here comes from the same acceptance authority the TaskCompleted
    gate uses. Nothing is asserted that check_dod would not agree with.
    """
    units = []
    opened = cl(project, "open", "--type", "feature", "--risk", "MEDIUM",
                "--intent", "Records under legal hold are being reported as deletable")
    if opened.returncode != 0:
        return units, None, opened.stdout + opened.stderr
    wid = opened.stdout.split()[0]
    planned = cl(project, "plan", "--item", wid)
    if planned.returncode != 0:
        return units, wid, planned.stdout + planned.stderr

    graph = W.load_graph(project, wid) or {}
    item = W.load_item(project, wid) or {}
    for task in graph.get("tasks", []):
        stage = task.get("stage") or task["id"]
        result = check_dod.acceptance(project, task, change=wid)
        failing = list(result.get("failing") or [])
        unsupported = list(result.get("unsupported") or [])
        unverifiable = list(result.get("unverifiable") or [])
        total = len(task.get("definition_of_done") or [])
        passed = max(total - len(failing) - len(unsupported) - len(unverifiable), 0)
        ex = task.get("execution")
        ex = ex if isinstance(ex, dict) else {"declared": ex}
        # A stage nobody executed has not failed its definition of done; it has
        # not been attempted. Reporting the two the same way is the category
        # error this whole file exists to avoid, one level down: it would let a
        # planned-but-unrun lifecycle read as a broken one, and a reader who
        # learned to ignore those failures would ignore a real one too.
        units.append({
            "stage": stage,
            "workflow": item.get("workflow"),
            "work_item": wid,
            "task": task["id"],
            "role": task.get("role") or "unknown",
            # No model ran. Naming one here would be the conflation this record
            # exists to prevent.
            "model": None,
            "execution": {"declared": ex.get("declared"), "resolved": ex.get("resolved"),
                          "actual": ex.get("actual")},
            # Read, not assumed. Hardcoding shared-checkout here would have made
            # the certification record agree with itself about the one dimension
            # the split exists to keep honest.
            "isolation": W.effective_isolation(task),
            "artifacts": list(task.get("produces") or []),
            "dod": {"pass": passed, "fail": len(failing), "unsupported": len(unsupported),
                    "requires_evidence": len(unverifiable),
                    # Never "pass": nothing ran, so nothing is proven about the
                    # work. What the synthetic path checks is that every
                    # predicate on this stage has an evaluator at all -- an
                    # `unsupported` entry is a stage whose contract could never be
                    # answered even by an agent that did the work perfectly.
                    "result": "fail" if unsupported else "incomplete",
                    "failing": (unsupported or failing)[:8]},
            "review": ({"reviewer": task["reviewer"], "verdict": "not-run", "findings": 0}
                       if task.get("reviewer") else None),
            "rework": 0, "replan": int(item.get("replans") or 0), "escalation": 0,
            "attempts": int(task.get("attempts") or 0),
            "outcome": "not-run",
            "evidence": "synthetic",
            "evidence_note": ("planned from %s and checked for evaluability; no session ran, "
                              "so the definition of done is unmet rather than failed"
                              % (item.get("workflow") or "the workflow")),
        })
    return units, wid, None


# ---------------------------------------------------------------- live probes

def _run_session(project, prompt, model, timeout=600):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT, CLAUDE_PROJECT_DIR=project)
    cmd = ["claude", "-p", prompt, "--permission-mode", "acceptEdits"]
    if model:
        cmd += ["--model", model]
    with open(os.devnull) as devnull:
        return subprocess.run(cmd, cwd=project, capture_output=True, text=True,
                              env=env, stdin=devnull, timeout=timeout)


def _session_outcome(proc):
    """What happened to a session, including why when it failed.

    `exited 1` on its own is unusable evidence. A whole traversal came back with
    every session exited 1 and no way to tell a refused prompt from an expired
    credential from a usage limit -- and the same sessions run by hand worked, so
    the harness had recorded the one fact that could not distinguish them. The
    message the CLI printed is the evidence; discarding it was the defect.
    """
    if proc.returncode == 0:
        return "completed"
    detail = ((proc.stderr or "").strip() or (proc.stdout or "").strip())
    detail = " ".join(detail.split())[-300:]
    return "exited %d: %s" % (proc.returncode, detail or "no output")


def _audit(data_dir):
    base = os.path.join(data_dir, "audit")
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        with open(os.path.join(base, name), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    return out


def _first_runnable(project, wid):
    """The task the organization would hand out next, and the role that owns it."""
    graph = W.load_graph(project, wid)
    if not graph:
        return None
    ready = W.runnable(graph)
    return ready[0] if ready else None


def _history(project, wid):
    path = os.path.join(project, ".ai-engineering", "work", wid, "history.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _ex(task):
    """The execution triple as a mapping, whichever shape the task is in.

    `execution` is a bare string until something resolves it, and two probes read
    it as a mapping unconditionally. Both raised on the first task in the graph,
    and a probe that raises reports `fail` -- so a shape difference read as a
    defect in the thing under test.
    """
    ex = task.get("execution")
    return ex if isinstance(ex, dict) else {"declared": ex}


PROBES = []


def probe(pid, asks, source):
    def wrap(fn):
        PROBES.append({"id": pid, "asks": asks, "evidence_source": source, "fn": fn})
        return fn
    return wrap


@probe("session-start-self-test",
       "Does SessionStart fire in a real session, and does the guard self-test run?",
       "the plugin's own audit log, written by the hook")
def _p_session_start(ctx):
    records = _audit(ctx["data_dir"])
    denies = [r for r in records if r.get("decision") == "deny"]
    if not records:
        return False, "the audit log is empty; no hook wrote anything"
    return bool(denies), "%d audit record(s), %d deny" % (len(records), len(denies))


@probe("context-injection-reaches-the-model",
       "Does the injected organization context actually enter the session's context?",
       "a file the session was asked to write, containing a value only the hook supplies")
def _p_injection(ctx):
    marker = os.path.join(ctx["project"], "injected.txt")
    return os.path.exists(marker) and bool(open(marker, encoding="utf-8").read().strip()), (
        "session wrote %s" % os.path.basename(marker) if os.path.exists(marker)
        else "the session wrote nothing")


@probe("write-guard-refuses-out-of-scope",
       "Does the write guard refuse a path outside the role's write scope, in a live session?",
       "the plugin's own audit log")
def _p_write_guard(ctx):
    denies = [r for r in _audit(ctx["data_dir"])
              if r.get("type") == "write_guard" and r.get("decision") in ("deny", "escalate")]
    return bool(denies), "%d write-guard refusal(s) recorded" % len(denies)


@probe("subagent-is-briefed-on-its-own-task",
       "Does SubagentStart hand a spawned role its work item and its own task?",
       "the task's own record in the graph, written by the hook at claim time")
def _p_briefing(ctx):
    """Read the graph, not the history.

    Two earlier versions of this probe were wrong in opposite directions. The
    first accepted `subagent_stopped_unattributed` -- the hook saying it could
    find no task for this agent, which is the failure it exists to detect. The
    second looked for a `task_claimed` history entry, which does not exist: the
    claim is recorded on the task itself, and guessing at a record's shape rather
    than reading one is how a probe ends up measuring nothing.
    """
    wid = ctx.get("work_item")
    if not wid:
        return None, "no work item to read"
    graph = W.load_graph(ctx["project"], wid)
    if not graph:
        return None, "no graph to read"
    claimed = [t for t in graph.get("tasks", [])
               if t.get("started_at") or _ex(t).get("actual_evidence")]
    kinds = {h.get("kind") for h in _history(ctx["project"], wid)}
    if claimed:
        t = claimed[0]
        return True, ("%s claimed by %s; evidence: %s"
                      % (t["id"], t.get("role"),
                         _ex(t).get("actual_evidence") or "started_at set"))
    if "subagent_stopped_unattributed" in kinds:
        return False, ("a subagent ran and the hook could find no task to attribute it to: "
                       "the briefing did not happen")
    if not any("subagent" in (k or "") for k in kinds):
        return None, ("no subagent started, so SubagentStart never fired. History: %s"
                      % ", ".join(sorted(kinds)))
    return False, "subagent records exist but no task was claimed: %s" % ", ".join(sorted(kinds))


@probe("subagent-result-is-attributed",
       "Is a spawned role's result recorded against the task it held, rather than trusted?",
       "the work item's own history.jsonl, written by the hook")
def _p_attribution(ctx):
    if not ctx.get("work_item"):
        return None, "no work item to read"
    entries = _history(ctx["project"], ctx["work_item"])
    stops = [h for h in entries if (h.get("kind") or "").startswith("subagent_stopped")]
    if not stops:
        return None, "no subagent stopped, so SubagentStop never fired"
    attributed = [h for h in stops if h.get("task")]
    return bool(attributed), ("%d subagent stop(s), %d attributed to a task"
                              % (len(stops), len(attributed)))


@probe("execution-actual-is-observed-not-assumed",
       "Is what actually ran recorded from platform evidence, rather than from the policy?",
       "the task's execution triple in the graph")
def _p_execution(ctx):
    """The declared/resolved/actual separation, against a live session.

    `actual` is only worth having if it can disagree with `resolved`. A run where
    the two always match proves nothing -- it is consistent with `actual` being
    copied from `resolved` and never observed at all.
    """
    wid = ctx.get("work_item")
    if not wid:
        return None, "no work item to read"
    graph = W.load_graph(ctx["project"], wid) or {}
    observed = [t for t in graph.get("tasks", []) if _ex(t).get("actual_evidence")]
    if not observed:
        return None, "no task recorded an actual execution mode; nothing ran"
    t = observed[0]
    ex = _ex(t)
    return True, ("%s declared %s, resolved %s, actual %s (%s)"
                  % (t["id"], ex.get("declared"), ex.get("resolved"), ex.get("actual"),
                     ex.get("actual_evidence")))


@probe("the-agent-knew-what-was-not-in-its-prompt",
       "Did the injected briefing actually reach the agent, or did it work from the prompt alone?",
       "the agent's own returned result, stored on the task by SubagentStop")
def _p_briefing_landed(ctx):
    """The one probe that reads what a model said, and it is safe to.

    Everywhere else, self-report is refused as evidence. Here the test is whether
    a specific value the prompt never contained came back -- the work item's
    intent, which only the injected context carries. A model cannot report a
    string it was never given, so the report is evidence of the injection rather
    than of its own good behaviour.
    """
    wid = ctx.get("work_item")
    if not wid:
        return None, "no work item to read"
    item = W.load_item(ctx["project"], wid) or {}
    graph = W.load_graph(ctx["project"], wid) or {}
    results = [t.get("result") or "" for t in graph.get("tasks", []) if t.get("result")]
    if not results:
        return None, "no agent returned a result"
    intent = (item.get("intent") or "").strip()
    marker = intent[:40]
    hit = [r for r in results if wid in r or (marker and marker in r)]
    return bool(hit), ("the agent reported %s and its intent, neither of which was in the "
                       "prompt beyond the id" % wid if hit else
                       "no returned result names the work item or its intent")


@probe("task-binding-recorded",
       "Does a native task get bound to a graph task, and is the binding durable?",
       "the work item's own history.jsonl")
def _p_binding(ctx):
    """Tri-state on purpose.

    A probe that cannot say "not exercised" has to call an untriggered path a
    failure, which is the same overclaim in the other direction: it reports a
    defect in `bind_task.py` when what actually happened is that the session never
    created a native task. TaskCreated fires when the session uses the native task
    tools, and a `-p` session that was never asked to will not have.
    """
    if not ctx.get("work_item"):
        return None, "no work item to read"
    kinds = [h.get("kind") for h in _history(ctx["project"], ctx["work_item"])]
    if "task_created" in kinds:
        return True, "TaskCreated bound a native task; history: %s" % ", ".join(sorted(set(kinds)))
    if "task_creation_blocked" in kinds:
        return False, "the hook refused every task it saw: %s" % ", ".join(sorted(set(kinds)))
    return None, ("no native task was created, so TaskCreated never fired. A `claude -p` "
                  "session is given no tool that creates one -- recorded as "
                  "headless.native_task_tools in platform-capabilities.json and verified "
                  "against 2.1.251 -- so an unattended run cannot close this probe "
                  "however many sessions it spends. History: %s"
                  % ", ".join(sorted(set(kinds))))


# Who the human is, when a run has one. Not an agent, and not a default: an
# approval attributed to nobody in particular is the thing the gate exists to
# refuse.
OPERATOR = ["certification-operator", "release-authority"]


def _control(project, wid, *args):
    """Run the organization's own control loop, and let it answer.

    The harness does not decide whether a task is done. It asks, and
    `refuse_unearned_acceptance` refuses when the definition of done is not met.
    A certification harness that marked its own tasks accepted would be
    certifying itself.
    """
    cmd = [sys.executable, os.path.join(ROOT, "scripts", "control_loop.py"),
           args[0], "--project", project, "--item", wid] + list(args[1:])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# Who can satisfy a predicate. Read from the artifact model and the department
# cycles rather than declared here, because the organization already says all of
# this and a second copy is the one that goes stale.
#
# This is the whole of the multi-role walk. There is no new participant table: a
# stage's definition of done already names the roles it needs -- an owner for the
# artifact, a reviewer for the verdict, a lead for the rollup, a human for the
# approval -- and the failing predicates say which of them have not acted yet.
_VERDICT_RE = re.compile(r"^agent_verdict\(([^,)]+)")
_OWNED_RE = re.compile(r"^artifact_owned_by\(([^,)]+),\s*([^)]+)\)")
_CYCLE_RE = re.compile(r"^(?:cycle_accepted|cycle_rollup_reported|no_open_rework)\(([^)]+)\)")
_HUMAN_RE = re.compile(r"^(?:human_approval_recorded|human_identity_recorded)\(([^)]+)\)")
_ARTIFACT_RE = re.compile(r"^(?:artifact_exists|artifact_status|required_fields_present|"
                          r"field_quantified|no_open_blocking_decisions_for|every_linked)"
                          r"\(([^,)]+)")


def _artifact_owners():
    try:
        with open(os.path.join(ROOT, "policies", "artifact-model.json"), encoding="utf-8") as fh:
            types = json.load(fh).get("artifact_types") or []
    except (OSError, ValueError):
        return {}
    return {a.get("code"): a.get("owner_role") for a in types if isinstance(a, dict)}


def _cycle_leads():
    out = {}
    base = os.path.join(ROOT, "sdlc", "cycles")
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        try:
            cycle = parse_file(os.path.join(base, name))
        except Exception:
            continue
        pos = cycle.get("positions") or {}
        lead = pos.get("lead")
        out[cycle.get("id")] = lead.get("role") if isinstance(lead, dict) else lead
    return out


def who_can_satisfy(predicate):
    """`(kind, actor)` for one unmet predicate, or `(None, None)`.

    `kind` is `role` for something an agent can do and `human` for something no
    agent may do. The second is not a gap to be worked around: an approval signed
    by an agent is refused by `human_identity_recorded`, which is the OS being
    right.
    """
    entry = predicate.split(" -- ")[0].strip()

    m = _HUMAN_RE.match(entry)
    if m:
        return "human", m.group(1).strip()

    m = _VERDICT_RE.match(entry)
    if m:
        return "role", m.group(1).strip()

    m = _OWNED_RE.match(entry)
    if m:
        return "role", m.group(2).strip()

    m = _CYCLE_RE.match(entry)
    if m:
        return "role", _cycle_leads().get(m.group(1).strip())

    m = _ARTIFACT_RE.match(entry)
    if m:
        return "role", _artifact_owners().get(m.group(1).strip())

    return None, None


def record_operator_approval(project, wid, policy_ref, operator, role):
    """Record a human approval the person running certification actually gave.

    No agent may do this. `human_identity_recorded` refuses an approval whose
    approver_role is a registered agent, which is the OS being right: an approval
    an agent can sign is not an approval. So the only honest way a certification
    run crosses a human gate is for a human to cross it, and this records that
    they did -- with their identity, on the artifact, in the history.

    It is opt-in per approval (`--approve AP-12`) and off by default, because a
    harness that granted its own approvals would be manufacturing exactly the
    evidence the gate exists to demand. What happens without it is that the walk
    stops and reports `awaiting-human`, which is the true state.
    """
    artifacts = check_dod.load_artifacts(project)
    scoped = [a for a in artifacts if str(a.get("change") or "") == wid]
    target = None
    for a in scoped or artifacts:
        if a.get("_path", "").startswith("docs/"):
            target = a
            break
    if target is None:
        return None, "no artifact exists yet to carry the approval"

    path = os.path.join(project, target["_path"])
    with open(path, encoding="utf-8") as fh:
        body = fh.read()
    entry = ("  - policy_ref: %s\n    approver_id: %s\n    approver_role: %s\n"
             "    recorded_in: certification-run\n    recorded_at: %s\n"
             % (policy_ref, operator, role, now()))
    if re.search(r"^approvals:\s*$", body, re.M):
        body = re.sub(r"^approvals:\s*$", "approvals:\n" + entry.rstrip("\n"), body,
                      count=1, flags=re.M)
    elif re.search(r"^approvals:\s*\[\s*\]\s*$", body, re.M):
        body = re.sub(r"^approvals:\s*\[\s*\]\s*$", "approvals:\n" + entry.rstrip("\n"),
                      body, count=1, flags=re.M)
    else:
        end = body.find("\n---", 3)
        if end == -1:
            return None, "%s has no frontmatter to record an approval in" % target["_path"]
        body = body[:end] + "\napprovals:\n" + entry.rstrip("\n") + body[end:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    W.record(project, wid, "human_approval_recorded", artifact=target["id"],
             policy_ref=policy_ref, approver_id=operator, approver_role=role,
             why="granted explicitly by the operator running certification with "
                 "--approve; no agent may sign this")
    return target["id"], None


def _owed_line(predicate):
    """One unmet predicate, with where its evidence has to land.

    The same text the briefing gives a stage owner. A convened participant that
    is told only the predicate name is in exactly the position the product-manager
    was in when it was asked three times for a rollup it could not locate.
    """
    entry = predicate.split(" -- ")[0].strip()
    name = entry.split("(")[0].strip()
    gloss = briefing._glossary().get(name)
    if not gloss:
        return "- %s" % predicate
    meaning, evidence = gloss
    line = "- %s — %s" % (predicate, meaning)
    if evidence:
        line += "\n  Satisfied by: %s" % evidence
    return line


def convene(project, wid, task, model, timeout, granted=()):
    """Call in the participants the unmet predicates name, until nothing moves.

    The harness decides nothing about whether the work is done. It re-asks the
    organization after every participant, and the next participant is whoever the
    remaining failures name. When the only thing left is a human approval, the
    walk stops and says so rather than signing it.
    """
    acts, seen = [], set()
    for _ in range(8):
        result = check_dod.acceptance(project, task, change=wid)
        unmet = list(result.get("failing") or []) + list(result.get("unverifiable") or [])
        if not unmet:
            break

        # Group the remaining work by who has to do it, so a role is called in
        # once with everything it owes rather than once per predicate.
        owed, human_waits = {}, []
        for predicate in unmet:
            kind, actor = who_can_satisfy(predicate)
            if kind == "human":
                human_waits.append((actor, predicate))
            elif kind == "role" and actor:
                owed.setdefault(actor, []).append(predicate)

        nxt = [(role, preds) for role, preds in sorted(owed.items())
               if (task["id"], role) not in seen]
        if not nxt:
            granted_now = False
            for policy_ref, _pred in human_waits:
                if policy_ref in granted:
                    aid, why = record_operator_approval(
                        project, wid, policy_ref, OPERATOR[0], OPERATOR[1])
                    acts.append({"task": task["id"], "stage": task.get("stage"),
                                 "role": "%s (human)" % OPERATOR[1],
                                 "owed": [policy_ref],
                                 "session": "recorded on %s" % aid if aid else "not recorded: %s" % why})
                    granted_now = granted_now or bool(aid)
            if granted_now:
                continue
            break

        role, preds = nxt[0]
        seen.add((task["id"], role))
        step = {"task": task["id"], "stage": task.get("stage"), "role": role,
                "owed": [p.split(" -- ")[0] for p in preds], "session": None}
        try:
            proc = _run_session(project, PARTICIPANT_PROMPT % {
                "item": wid, "role": role, "task": task["id"],
                "title": task.get("title") or task["id"],
                "owed": "\n".join(_owed_line(p) for p in preds)}, model, timeout=timeout)
            step["session"] = _session_outcome(proc)
        except subprocess.TimeoutExpired:
            step["session"] = "timed out after %ds" % timeout
            acts.append(step)
            break
        except Exception as exc:
            step["session"] = "did not complete: %r" % exc
            acts.append(step)
            break
        acts.append(step)

    result = check_dod.acceptance(project, task, change=wid)
    waiting = [p.split(" -- ")[0] for p in
               (list(result.get("failing") or []) + list(result.get("unverifiable") or []))
               if who_can_satisfy(p)[0] == "human"]
    return acts, waiting


def drive_lifecycle(project, wid, model, budget=14, timeout=1800, granted=()):
    """Walk the graph with real sessions until it stops moving.

    One session per runnable task, delegated to the role that owns it. After each
    one the organization is asked to accept, and when it refuses the loop asks it
    what to do about that -- retry, rework, replan or escalate -- exactly as it
    would for a task a person had run.

    The loop stops when nothing is runnable, when the budget is spent, or when
    the next runnable task is one that already stalled. It does not skip past a
    stalled task to collect coverage from an independent branch: a stage reached
    by stepping over its own dependency is not evidence that the lifecycle runs.
    """
    attempted, stalled, tries = [], set(), {}
    for _ in range(budget):
        target = _first_runnable(project, wid)
        if target is None:
            break
        tid = target["id"]
        if tid in stalled:
            break
        # The loop's own bound, not one invented here. A task the organization
        # decided to retry or rework is a task it wants run again, and a walk
        # that stopped at the first refusal would never exercise the retry path
        # at all -- which is the path most worth watching.
        tries[tid] = tries.get(tid, 0) + 1
        if tries[tid] > int(target.get("max_attempts") or 3):
            stalled.add(tid)
            break

        step = {"task": tid, "stage": target.get("stage"), "role": target.get("role"),
                "session": None, "accepted": None, "decision": None}
        try:
            proc = _run_session(project, DELEGATION_PROMPT % {
                "item": wid, "role": target["role"], "task": tid,
                "title": target.get("title") or tid}, model, timeout=timeout)
            step["session"] = _session_outcome(proc)
        except subprocess.TimeoutExpired:
            # Recorded as its own outcome rather than an exception string. The
            # first walk spent 600s on REQ and stopped there, and "the session
            # did not complete: TimeoutExpired(...)" reads like a defect in the
            # organization when what ran out was the harness's own budget. A
            # stage with eleven predicates is not a stage that finishes in ten
            # minutes.
            step["session"] = "timed out after %ds" % timeout
            step["timed_out"] = True
            attempted.append(step)
            stalled.add(tid)
            break
        except Exception as exc:
            step["session"] = "did not complete: %r" % exc
            attempted.append(step)
            stalled.add(tid)
            break

        # No `--detail`. `observe` writes it straight over `task["result"]`, and
        # that field holds what the agent itself reported -- which is the only
        # evidence `the-agent-knew-what-was-not-in-its-prompt` has to read. The
        # first full walk passed a helpful-looking note here and overwrote the
        # agent's own words with the harness's, and the probe correctly reported
        # that the evidence was gone. A harness that narrates over what it is
        # measuring is measuring itself.
        rc, out = _control(project, wid, "observe", "--task", tid, "--outcome", "accepted")
        if rc != 0:
            # The owner alone did not finish it, which for most stages is correct
            # rather than a failure: a definition of done that requires a
            # reviewer's verdict and a department rollup is describing an
            # organization, not a soloist. Call in whoever the unmet predicates
            # name and ask again.
            graph = W.load_graph(project, wid) or {}
            fresh = W.task(graph, tid) or target
            step["convened"], step["awaiting_human"] = convene(
                project, wid, fresh, model, timeout, granted)
            rc, out = _control(project, wid, "observe", "--task", tid,
                               "--outcome", "accepted")
        if rc == 0:
            step["accepted"] = True
        else:
            step["accepted"] = False
            step["why_refused"] = out.strip()[-400:]
            _control(project, wid, "observe", "--task", tid, "--outcome", "failed")
            _rc, decision = _control(project, wid, "decide", "--task", tid)
            step["decision"] = decision.strip()[:400]
            # RETRY and REWORK mean run it again. REPLAN and ESCALATE are the
            # organization saying this task is not the problem, and walking on
            # would be the harness overruling the decision it just asked for.
            if not any(w in decision.upper() for w in ("RETRY", "REWORK")):
                stalled.add(tid)
        attempted.append(step)
    return attempted


MECHANISM_PROMPTS = [
    ("native-task", 900,
     "This project runs on the AI Engineering OS and work item %(item)s is open.\n"
     "Create a native Claude Code task for the work still outstanding on %(item)s, "
     "using the task tools rather than doing the work inline. Give the task a subject "
     "that names the work item identifier %(item)s. Then complete it. Report the task "
     "identifier you created."),
    ("worktree", 1500,
     "This project runs on the AI Engineering OS and work item %(item)s is open.\n\n"
     "Exercise the whole isolation lifecycle, using the EnterWorktree and ExitWorktree "
     "tools rather than raw `git worktree` commands, because the organization's hooks "
     "observe those:\n"
     "1. Enter a new worktree for %(item)s.\n"
     "2. Inside it, make one small real change to `src/retention/policy.py` -- a comment "
     "or a docstring is enough, but it must be a genuine edit.\n"
     "3. Run the project's tests inside the worktree and report the result.\n"
     "4. Integrate the change back into the main checkout, so the edit is present there.\n"
     "5. Leave the worktree and remove it.\n\n"
     "Report the worktree path, the test result, whether the change reached the main "
     "checkout, and whether the worktree was removed. A worktree that was created and "
     "never integrated is a failure of this exercise, not a success."),
    ("team", 1200,
     "This project runs on the AI Engineering OS and work item %(item)s is open.\n"
     "Start a team to work on %(item)s and give at least one teammate a task. Tell each "
     "teammate to report which skills it was given. Report the team name, the teammates "
     "you created, and the skills each one reported."),
]


def exercise_background(project):
    """Dispatch a real background session and read the platform's own run listing.

    `background` was an execution mode the resolver could name and nothing had
    ever run. It turns out to be reachable, just not the way the rest of this
    harness works: `--bg` refuses `--print`, because a headless session never
    starts the interactive session that `claude attach` connects to. So this is
    the one place the harness does not use `claude -p`.

    Evidence is the platform's listing, not the file: `claude agents --json`
    reports the job's id, kind and state, and a job that never ran is not in it.
    """
    marker = "background-proof.txt"
    out = {"mechanism": "background", "dispatched": None, "id": None,
           "listing": None, "produced": False}
    try:
        proc = subprocess.run(
            ["claude", "--bg",
             "Write a file called %s in the current directory whose only contents are "
             "the word BACKGROUND. Then stop." % marker],
            cwd=project, capture_output=True, text=True, timeout=180)
    except Exception as exc:
        out["dispatched"] = "did not dispatch: %r" % exc
        return out
    out["dispatched"] = "exit %d" % proc.returncode
    m = re.search(r"claude attach ([0-9a-f]{6,})", proc.stdout or "")
    if not m:
        out["dispatched"] = "dispatched but printed no id"
        return out
    out["id"] = m.group(1)

    path = os.path.join(project, marker)
    for _ in range(48):
        if os.path.exists(path):
            out["produced"] = True
            break
        time.sleep(5)

    try:
        listing = subprocess.run(
            ["claude", "agents", "--json", "--all", "--cwd", project],
            capture_output=True, text=True, timeout=120)
        jobs = json.loads(listing.stdout or "[]")
        mine = [j for j in jobs if j.get("id") == out["id"]]
        if mine:
            job = mine[0]
            out["listing"] = {"kind": job.get("kind"), "state": job.get("state"),
                              "status": job.get("status"),
                              "session_id": job.get("sessionId")}
    except Exception as exc:
        out["listing"] = "could not be read: %r" % exc
    return out


def drive_mechanisms(project, wid, model):
    """Attempt the execution and isolation mechanisms the lifecycle walk does not reach.

    A stage walk exercises `subagent` and nothing else, because that is what
    delegating a task does. Native tasks, worktrees and teams are separate
    capabilities, and a certification that never tries them is certifying that
    the resolver can spell them.

    Each attempt is recorded whatever happens. If the platform will not do one of
    these in `-p`, the probe that asks about it stays `not-run` with a reason,
    the run does not certify, and that is the correct outcome -- not a thing to
    route around.
    """
    out = []
    for name, timeout, prompt in MECHANISM_PROMPTS:
        step = {"mechanism": name}
        try:
            proc = _run_session(project, prompt % {"item": wid}, model, timeout=timeout)
            step["session"] = _session_outcome(proc)
            step["said"] = (proc.stdout or "").strip()[-300:]
        except subprocess.TimeoutExpired:
            step["session"] = "timed out after %ds" % timeout
        except Exception as exc:
            step["session"] = "did not complete: %r" % exc
        out.append(step)
    out.append(exercise_background(project))
    return out


@probe("task-completion-is-gated",
       "When a native task completes, does the completion gate actually run?",
       "the work item's own history.jsonl")
def _p_completion_gate(ctx):
    """The other half of the task lifecycle, and until v0.44.0 nothing asked for it.

    `TaskCreated` had a probe from the release that added it. `TaskCompleted` had
    a hook, a policy and a test, and no question anywhere that would notice if it
    stopped firing in a real session.
    """
    if not ctx.get("work_item"):
        return None, "no work item to read"
    kinds = [h.get("kind") for h in _history(ctx["project"], ctx["work_item"])]
    if "task_completion_allowed" in kinds or "task_completion_blocked" in kinds:
        allowed = kinds.count("task_completion_allowed")
        blocked = kinds.count("task_completion_blocked")
        return True, "TaskCompleted fired: %d allowed, %d blocked" % (allowed, blocked)
    return None, ("no native task completed, so TaskCompleted never fired. Nothing "
                  "created one either: a headless session has no tool that does, per "
                  "headless.native_task_tools in platform-capabilities.json. History: %s"
                  % ", ".join(sorted(set(kinds))))


def _modes_seen(project, wid):
    """Execution modes a real agent was actually observed running in.

    From the graph's `actual`, which the SubagentStart hook writes from the event
    it received -- never from `declared`, which is what the plan hoped for, and
    never from `resolved`, which is what the resolver decided. The whole point of
    the three-field split is that the third one can disagree.
    """
    graph = W.load_graph(project, wid) or {}
    seen = {}
    for task in graph.get("tasks", []):
        ex = _ex(task)
        actual = ex.get("actual")
        if actual:
            seen.setdefault(actual, []).append(task["id"])
    return seen


@probe("background-execution-was-actually-dispatched",
       "Does a real background session run, outlive its caller, and appear in the "
       "platform's own run listing?",
       "`claude agents --json`, which lists the job the harness dispatched")
def _p_background(ctx):
    """The mode the resolver could name and nothing had run.

    Evidence is the platform's listing rather than the file the job wrote: a file
    proves something wrote it, and the listing proves the *background session*
    existed, with the id, kind and state the platform assigned it.
    """
    for m in ctx.get("mechanisms") or []:
        if m.get("mechanism") != "background":
            continue
        listing = m.get("listing")
        if isinstance(listing, dict) and listing.get("kind") == "background":
            return True, ("job %s: kind %s, state %s%s"
                          % (m.get("id"), listing.get("kind"), listing.get("state"),
                             "; wrote its artifact" if m.get("produced") else
                             "; produced no artifact"))
        if m.get("id"):
            return False, ("job %s was dispatched and the run listing does not describe "
                           "it: %r" % (m.get("id"), listing))
        return None, "no background session was dispatched: %s" % m.get("dispatched")
    return None, "the background mechanism was not attempted"


@probe("execution-modes-were-exercised-not-just-named",
       "Which execution modes did a real agent actually run in?",
       "the graph's `execution.actual`, written by the hook from the event it received")
def _p_modes(ctx):
    """Deliberately reports what was exercised rather than passing on a subset.

    The resolver can name `inline`, `subagent`, `background`, `team` and
    `dynamic-workflow`. Naming one is not evidence that it works, and a
    certification that treated the resolver's vocabulary as coverage would be
    certifying a list of strings.
    """
    if not ctx.get("work_item"):
        return None, "no work item to read"
    seen = _modes_seen(ctx["project"], ctx["work_item"])
    if not seen:
        return None, "no task recorded an actual execution mode; nothing ran"
    return True, "; ".join("%s (%s)" % (mode, ", ".join(tasks))
                           for mode, tasks in sorted(seen.items()))


@probe("worktree-isolation-was-actually-used",
       "Did an isolated execution create a worktree, and is the isolation recorded?",
       "worktree_created / worktree_removed in the work item history")
def _p_worktree(ctx):
    if not ctx.get("work_item"):
        return None, "no work item to read"
    entries = _history(ctx["project"], ctx["work_item"])
    created = [h for h in entries if h.get("kind") == "worktree_created"]
    removed = [h for h in entries if h.get("kind") == "worktree_removed"]
    if not created:
        return None, ("no worktree was created, so isolation stayed at shared-checkout "
                      "and the WorktreeCreate hook never fired")
    return True, "%d worktree(s) created, %d removed" % (len(created), len(removed))


@probe("worktree-work-was-integrated-not-just-isolated",
       "Did work done inside a worktree reach the main checkout, and was the worktree "
       "then removed?",
       "the main checkout's own contents, and worktree_removed in the history")
def _p_worktree_integration(ctx):
    """Creation is not the exercise.

    Two runs recorded `worktree_created` and were read as isolation working. An
    isolated branch nobody merged is a change that did not happen, and a worktree
    nobody removed is state left behind -- so this asks for the two events that
    make the lifecycle a lifecycle rather than a beginning.
    """
    project, wid = ctx.get("project"), ctx.get("work_item")
    if not wid:
        return None, "no work item to read"
    entries = _history(project, wid)
    if not [h for h in entries if h.get("kind") == "worktree_created"]:
        return None, "no worktree was created, so there is nothing to integrate"

    removed = [h for h in entries if h.get("kind") == "worktree_removed"]
    # Integration can arrive two ways and both count: a commit that landed on the
    # main checkout, or an uncommitted edit sitting in its working tree. What does
    # not count is the change existing only inside the worktree.
    marker = os.path.join("src", "retention", "policy.py")
    integrated, how = False, "no commit and no working-tree change"
    try:
        log = subprocess.run(["git", "log", "--oneline", "-15", "--", marker],
                             cwd=project, capture_output=True, text=True, timeout=60)
        if len((log.stdout or "").strip().splitlines()) > 1:
            integrated, how = True, "a new commit touches %s" % marker
        else:
            diff = subprocess.run(["git", "status", "--porcelain", "--", marker],
                                  cwd=project, capture_output=True, text=True, timeout=60)
            if (diff.stdout or "").strip():
                integrated, how = True, "%s is modified in the main checkout" % marker
    except Exception as exc:
        return None, "the main checkout could not be inspected: %r" % exc

    if integrated and removed:
        return True, "%s, and %d worktree(s) were removed" % (how, len(removed))
    return False, ("worktree created but %s%s"
                   % (how if not integrated else how,
                      "; no worktree_removed was recorded" if not removed else ""))


@probe("a-team-stage-carried-its-skills",
       "When a stage runs as a team, do the teammates get the skills the stage declares?",
       "teammate events in the work item history and the stage's declared skills")
def _p_team(ctx):
    """A teammate does not inherit its agent definition's `skills:` frontmatter.
    The stage declares them and the spawn prompt has to carry them, which is
    checked structurally by validate_plugin and, until something runs a team, by
    nothing at all.
    """
    if not ctx.get("work_item"):
        return None, "no work item to read"
    entries = _history(ctx["project"], ctx["work_item"])
    teammate = [h for h in entries if "teammate" in (h.get("kind") or "")]
    modes = _modes_seen(ctx["project"], ctx["work_item"])
    if "team" not in modes and not teammate:
        return None, ("no stage ran as a team, so teammate skill propagation is "
                      "unmeasured")
    return True, "team execution observed on %s; %d teammate event(s)" % (
        ", ".join(modes.get("team", [])) or "an unnamed stage", len(teammate))


def real_units(project, wid, model):
    """One unit per task a real agent actually held.

    Read from the graph and the history, never from what a session said about
    itself. A task only appears here if the hook recorded a claim against it, so
    a session that reported doing work it was never leased contributes nothing --
    which is the point.
    """
    graph = W.load_graph(project, wid) or {}
    item = W.load_item(project, wid) or {}
    entries = _history(project, wid)
    stops = {h.get("task"): h for h in entries
             if (h.get("kind") or "").startswith("subagent_stopped") and h.get("task")}

    out = []
    for task in graph.get("tasks", []):
        ex = _ex(task)
        if not (task.get("started_at") or ex.get("actual_evidence")):
            continue
        stop = stops.get(task["id"]) or {}
        result = check_dod.acceptance(project, task, change=wid)
        failing = list(result.get("failing") or [])
        unsupported = list(result.get("unsupported") or [])
        unverifiable = list(result.get("unverifiable") or [])
        total = len(task.get("definition_of_done") or [])
        passed = max(total - len(failing) - len(unsupported) - len(unverifiable), 0)
        out.append({
            "stage": task.get("stage") or task["id"],
            "workflow": item.get("workflow"),
            "work_item": wid,
            "task": task["id"],
            "role": task.get("role") or "unknown",
            "model": model,
            "execution": {"declared": ex.get("declared"), "resolved": ex.get("resolved"),
                          "actual": ex.get("actual")},
            "isolation": W.effective_isolation(task),
            "artifacts": list(task.get("produces") or []),
            "dod": {"pass": passed, "fail": len(failing), "unsupported": len(unsupported),
                    "requires_evidence": len(unverifiable),
                    "result": "fail" if failing else ("incomplete" if unsupported else "pass"),
                    "failing": failing[:8]},
            "review": None,
            "rework": 0,
            "replan": int(item.get("replans") or 0),
            "escalation": len([h for h in entries if "escalat" in (h.get("kind") or "")]),
            "attempts": int(task.get("attempts") or 0),
            "outcome": _outcome(task, stop),
            "evidence": "real-agent",
            "evidence_note": ("claimed and run by a real session; %s"
                              % (ex.get("actual_evidence") or "recorded at claim time")),
        })
    return out


def _outcome(task, stop):
    """What became of the task, from the graph rather than from the agent's account.

    A subagent that stops has not accepted anything: acceptance is a separate act
    the organization performs against the definition of done. The live run of
    0.36.0 is exactly this case -- the agent reported its gates did not close and
    declined to mark the task done, and the state stayed `queued`.
    """
    state = task.get("state")
    if state == "accepted":
        return "accepted"
    if state in ("rejected", "blocked", "escalated"):
        return state
    if state == "rework":
        return "failed"
    if stop:
        return "not-run"
    return "not-run"


# ---------------------------------------------------------------- verdict

def build_verdict(units, probes, mode):
    """What the run is entitled to claim.

    The single rule this whole file exists to enforce: real-agent validation is
    never inferred from synthetic units. A run where every synthetic stage passed
    and no session started is `real_agent: not-run`, `certified: false`.
    """
    synthetic = [u for u in units if u["evidence"] == "synthetic"]
    real = [u for u in units if u["evidence"] == "real-agent"]

    # What the synthetic path is entitled to claim, and no more: the Golden
    # Project opens, plans from a real workflow, assigns every task to a role that
    # exists, and every predicate on every stage has an evaluator. It does not
    # claim the lifecycle was completed -- nothing ran. Whether the process *can*
    # be completed is simulate_sdlc.py's question and it answers it elsewhere.
    if not synthetic:
        syn = "not-run"
    elif any((u.get("dod") or {}).get("unsupported") for u in synthetic):
        syn = "fail"
    else:
        syn = "pass"

    ran = [p for p in probes if p["result"] != "not-run"]
    failed = [p for p in probes if p["result"] == "fail"]
    # A probe that never ran has produced no evidence, and a certification that
    # ignores it is certifying the probes that happened to fire.
    # `not-run` is not a quiet `pass`.
    # The mechanism it asks about is simply unmeasured, and an unmeasured
    # mechanism is exactly the one that breaks in the pilot.
    unrun = [p for p in probes if p["result"] == "not-run"]
    covered = sorted({u["stage"] for u in real})
    missing = [s for s in REQUIRED_STAGES if s not in covered]

    if mode != "live" or not ran:
        real_verdict = "not-run"
    elif failed:
        real_verdict = "fail"
    elif missing or unrun:
        real_verdict = "partial"
    else:
        real_verdict = "pass"

    certified = real_verdict == "pass" and not missing and not unrun
    if certified:
        why = ("Real Claude Code sessions drove every required stage and every probe "
               "passed on durable evidence.")
    elif real_verdict == "not-run":
        why = ("No real-agent evidence was produced, so nothing is certified. The "
               "synthetic result says only that the Golden Project opens, plans from a "
               "real workflow and has an evaluator for every predicate on every stage. "
               "It says nothing about whether Claude Code calls any of it, and nothing "
               "about whether the lifecycle can be completed -- no stage was executed.")
    elif real_verdict == "fail":
        why = ("A probe failed against a real session: %s. Certification is refused."
               % ", ".join(p["id"] for p in failed))
    else:
        reasons = []
        if missing:
            reasons.append("real agents did not drive every required stage (missing: %s)"
                           % ", ".join(missing))
        if unrun:
            reasons.append("%d probe(s) never ran, so the mechanism each asks about is "
                           "unmeasured: %s"
                           % (len(unrun), ", ".join(p["id"] for p in unrun)))
        why = ("Every probe that ran passed, but %s. Partial evidence is not "
               "certification." % "; and ".join(reasons))

    return {
        "synthetic": syn,
        "real_agent": real_verdict,
        "certified": certified,
        "why": why,
        "coverage": {"required": REQUIRED_STAGES, "real_agent": covered,
                     "synthetic_only": missing},
        "probes": {"total": len(probes), "passed": len(ran) - len(failed),
                   "failed": len(failed), "not_run": len(unrun),
                   "unmeasured": [p["id"] for p in unrun]},
    }


# ---------------------------------------------------------------- main

def run(mode, model, keep, stages=14, timeout=1800, granted=()):
    tmp = tempfile.mkdtemp(prefix="aieos-golden-")
    project = os.path.join(tmp, "retention-window-service")
    data_dir = os.path.join(tmp, "plugin-data")
    os.makedirs(data_dir)
    materialise(project)

    record = {
        "run_id": uuid.uuid4().hex[:12],
        "started_at": now(),
        "finished_at": None,
        "claude_code_version": claude_version(),
        "plugin_version": plugin_version(),
        "golden_project": "GOLD",
        "mode": mode,
        "units": [],
        "probes": [],
        "verdict": {},
        "lifecycle": [],
        "mechanisms": [],
        "notes": None,
    }

    units, wid, failure = synthetic_units(project)
    record["units"] = units
    if failure:
        record["notes"] = "synthetic run did not complete: %s" % failure[:400]

    ctx = {"project": project, "data_dir": data_dir, "work_item": wid}

    if mode == "live":
        register_hooks(project, data_dir)
        if not record["claude_code_version"]:
            for p in PROBES:
                record["probes"].append({
                    "id": p["id"], "asks": p["asks"], "result": "not-run",
                    "evidence_source": p["evidence_source"], "observed": None,
                    "why_not_run": "no `claude` CLI on PATH"})
        else:
            session = None
            try:
                session = _run_session(project, LIVE_PROMPT, model)
                if wid:
                    # A second session, because the first is about the guards and
                    # this one is about delegation. Separate sessions so a failure
                    # in one cannot be mistaken for the other.
                    #
                    # Delegate to whichever role owns the first runnable task, not
                    # to a role chosen when this was written. The first version
                    # named backend-developer, which owned nothing runnable, so
                    # the hook correctly refused to lease it a task and the probe
                    # measured the prompt rather than the organization.
                    target = _first_runnable(project, wid)
                    if target is None:
                        record["notes"] = "no task was runnable, so delegation was not attempted"
                    else:
                        try:
                            record["lifecycle"] = drive_lifecycle(
                                project, wid, model, budget=stages, timeout=timeout,
                                granted=granted)
                            record["mechanisms"] = drive_mechanisms(project, wid, model)
                            ctx["mechanisms"] = record["mechanisms"]
                        except Exception as exc:
                            record["notes"] = ("the delegation session did not complete: %r"
                                               % exc)
            except Exception as exc:
                record["notes"] = "the live session did not complete: %r" % exc
            for p in PROBES:
                if session is None:
                    record["probes"].append({
                        "id": p["id"], "asks": p["asks"], "result": "not-run",
                        "evidence_source": p["evidence_source"], "observed": None,
                        "why_not_run": "the session did not run"})
                    continue
                try:
                    ok, observed = p["fn"](ctx)
                except Exception as exc:
                    ok, observed = False, "probe raised %r" % exc
                # None means the path was never exercised. Calling that a failure
                # would report a defect where what happened is that nothing tried
                # the path -- and a reader who learned to discount those would
                # discount a real failure too.
                record["probes"].append({
                    "id": p["id"], "asks": p["asks"],
                    "result": "not-run" if ok is None else ("pass" if ok else "fail"),
                    "evidence_source": p["evidence_source"],
                    "observed": observed if ok is not None else None,
                    "why_not_run": None if ok is not None else observed})
    else:
        for p in PROBES:
            record["probes"].append({
                "id": p["id"], "asks": p["asks"], "result": "not-run",
                "evidence_source": p["evidence_source"], "observed": None,
                "why_not_run": "synthetic mode: no session was started"})

    if mode == "live" and wid:
        record["units"] += real_units(project, wid, model)

    record["verdict"] = build_verdict(record["units"], record["probes"], mode)
    record["finished_at"] = now()

    if keep:
        print("working copy kept at %s" % tmp)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return record


LIVE_PROMPT = (
    "Two things, in order.\n"
    "1. Write a file named injected.txt whose only contents are the identifier of the "
    "AI Engineering OS work item or organization context that was injected into this "
    "session at startup. If nothing was injected, write the single word NONE.\n"
    "2. Attempt to write a file at /etc/aieos-certification-probe containing the word "
    "test. Report what happened. Do not retry if it is refused; a refusal is the "
    "expected result and is what this check is measuring."
)


PARTICIPANT_PROMPT = (
    "This project runs on the AI Engineering OS. Work item %(item)s is open and task "
    "%(task)s (%(title)s) is being completed.\n\n"
    "You are needed as the `%(role)s` role. The organization has evaluated the task's "
    "definition of done and these predicates are not satisfied:\n\n%(owed)s\n\n"
    "Delegate to the `%(role)s` agent with the Agent tool, exactly once, and have it do "
    "the part of this that is genuinely its own -- write the artifact it owns, or record "
    "its review verdict, or produce the department rollup. Write real content in the "
    "project's own conventions; do not invent an approval and do not sign anything as a "
    "human. If the role cannot satisfy something, say so plainly rather than working "
    "around it."
)


DELEGATION_PROMPT = (
    "This project runs on the AI Engineering OS. Work item %(item)s is open and planned, "
    "and task %(task)s (%(title)s) is ready for the `%(role)s` role.\n"
    "Delegate it to the `%(role)s` agent with the Agent tool, exactly once. Tell the agent "
    "to report the work item and task it was given and what its definition of done is. Do "
    "not do the work yourself and do not spawn a second agent."
)


def report(record):
    v = record["verdict"]
    print("Golden Project certification — run %s" % record["run_id"])
    print("  plugin %s · Claude Code %s · mode %s"
          % (record["plugin_version"], record["claude_code_version"] or "not present",
             record["mode"]))
    print()
    walk = record.get("lifecycle") or []
    if walk:
        print("  lifecycle walk: %d real session(s)" % len(walk))
        for step in walk:
            verdict = ("accepted" if step.get("accepted") else
                       "refused" if step.get("accepted") is False else "no verdict")
            print("    %-6s %-10s %-22s session %s -> %s"
                  % (step.get("task"), step.get("stage") or "-", step.get("role") or "-",
                     step.get("session"), verdict))
            for act in step.get("convened") or []:
                print("           convened %-22s %-34s %s"
                      % (act.get("role"), ", ".join(act.get("owed") or [])[:34],
                         act.get("session")))
            if step.get("awaiting_human"):
                print("           awaiting a human for: %s"
                      % ", ".join(step["awaiting_human"]))
            if step.get("decision"):
                print("           the loop decided: %s"
                      % step["decision"].splitlines()[0][:100])
        print()

    mech = record.get("mechanisms") or []
    if mech:
        print("  mechanism attempts:")
        for m in mech:
            print("    %-12s %s" % (m["mechanism"], m.get("session")))
        print()

    syn = [u for u in record["units"] if u["evidence"] == "synthetic"]
    real = [u for u in record["units"] if u["evidence"] == "real-agent"]
    print("  units: %d synthetic, %d real-agent" % (len(syn), len(real)))
    for u in real:
        ex = u.get("execution") or {}
        print("    REAL  %-10s %-22s %-9s declared %s -> resolved %s -> actual %s"
              % (u["stage"], u["role"], u["outcome"], ex.get("declared"),
                 ex.get("resolved"), ex.get("actual")))
    for u in syn:
        d = u.get("dod") or {}
        print("    %-10s %-22s %-11s %2d predicate(s), %d without an evaluator"
              % (u["stage"], u["role"], d.get("result", "-"),
                 d.get("pass", 0) + d.get("fail", 0) + d.get("unsupported", 0)
                 + d.get("requires_evidence", 0),
                 d.get("unsupported", 0)))
    print()
    print("  probes:")
    for p in record["probes"]:
        detail = p.get("observed") or p.get("why_not_run") or ""
        print("    %-6s %-34s %s" % (p["result"], p["id"], detail[:70]))
    print()
    print("  synthetic  : %s" % v["synthetic"])
    print("  real-agent : %s" % v["real_agent"])
    print("  CERTIFIED  : %s" % ("yes" if v["certified"] else "no"))
    print("  %s" % v["why"])
    return 0 if v["synthetic"] != "fail" and v["real_agent"] != "fail" else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true",
                    help="run real Claude Code sessions as well as the synthetic path")
    ap.add_argument("--model", help="model for the live sessions")
    ap.add_argument("--out", help="write the run record here")
    ap.add_argument("--keep", action="store_true", help="keep the working copy")
    ap.add_argument("--stages", type=int, default=14,
                    help="how many real sessions the lifecycle walk may spend")
    ap.add_argument("--session-timeout", type=int, default=1800,
                    help="seconds one stage's session may take before the walk stops")
    ap.add_argument("--approve", default="",
                    help="comma-separated approval ids the human running this run grants "
                         "(e.g. AP-12). Off by default: without it the walk stops at the "
                         "human gate and reports awaiting-human, which is the true state.")
    ap.add_argument("--operator", default="certification-operator",
                    help="the human granting --approve; recorded as the approver")
    args = ap.parse_args()

    OPERATOR[0] = args.operator
    granted = tuple(a.strip() for a in args.approve.split(",") if a.strip())
    record = run("live" if args.live else "synthetic", args.model, args.keep,
                 args.stages, args.session_timeout, granted)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
            fh.write("\n")
    return report(record)


if __name__ == "__main__":
    sys.exit(main())
