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
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))

import check_dod  # noqa: E402
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
            "isolation": "shared-checkout",
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
    return None, ("the session created no native task, so TaskCreated never fired. "
                  "History: %s" % ", ".join(sorted(set(kinds))))


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
            "isolation": "shared-checkout",
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
    covered = sorted({u["stage"] for u in real})
    missing = [s for s in REQUIRED_STAGES if s not in covered]

    if mode != "live" or not ran:
        real_verdict = "not-run"
    elif failed:
        real_verdict = "fail"
    elif missing:
        real_verdict = "partial"
    else:
        real_verdict = "pass"

    certified = real_verdict == "pass" and not missing
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
        why = ("Probes passed but real agents did not drive every required stage. "
               "Missing: %s. Partial evidence is not certification." % ", ".join(missing))

    return {
        "synthetic": syn,
        "real_agent": real_verdict,
        "certified": certified,
        "why": why,
        "coverage": {"required": REQUIRED_STAGES, "real_agent": covered,
                     "synthetic_only": missing},
    }


# ---------------------------------------------------------------- main

def run(mode, model, keep):
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
                            _run_session(project, DELEGATION_PROMPT % {
                                "item": wid, "role": target["role"], "task": target["id"],
                                "title": target.get("title") or target["id"]}, model)
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
    args = ap.parse_args()

    record = run("live" if args.live else "synthetic", args.model, args.keep)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
            fh.write("\n")
    return report(record)


if __name__ == "__main__":
    sys.exit(main())
