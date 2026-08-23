"""Reading and writing the durable work item, its graph and its history.

The session is not the system of record. Everything here lives under the
project's `.ai-engineering/work/<id>/` in source control, so that deleting every
Claude session still leaves enough to say what is being built, what has happened,
what remains, and who owns the next action.

Nothing in this module talks to Claude Code. It is a file format and a state
machine; who executes the work is a separate question, answered by the execution
policy.
"""
import json
import os
import time

try:
    from minyaml import parse_file
    from yamlemit import dump_document as yaml_dumps
except ImportError:                                        # pragma: no cover
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from minyaml import parse_file
    from yamlemit import dump_document as yaml_dumps

WORK_DIR = os.path.join(".ai-engineering", "work")

# The task states, and which may follow which. A state machine that permits
# everything is a label, not a control.
TRANSITIONS = {
    "queued":      ("assigned", "blocked", "abandoned"),
    "assigned":    ("working", "blocked", "queued", "abandoned"),
    "working":     ("review", "waiting", "blocked", "rejected", "escalated", "abandoned"),
    "waiting":     ("working", "blocked", "escalated", "abandoned"),
    "blocked":     ("queued", "working", "escalated", "abandoned"),
    "review":      ("accepted", "rework", "rejected", "escalated"),
    "rework":      ("working", "escalated", "abandoned"),
    "rejected":    ("rework", "escalated", "abandoned"),
    "escalated":   ("queued", "working", "abandoned", "accepted"),
    "accepted":    (),
    "abandoned":   (),
}
TERMINAL = ("accepted", "abandoned")

# Edges that are real but must be taken deliberately, never routed through on the
# way to somewhere else. A human accepting an escalated task is a legitimate
# outcome; a shortest-path search discovering that "queued -> blocked ->
# escalated -> accepted" is two hops cheaper than doing the work is not. Naming
# them keeps the edge available to a caller that means it, and out of the reach of
# a search that does not.
DELIBERATE_ONLY = {
    ("escalated", "accepted"),
    ("blocked", "escalated"),
    ("waiting", "escalated"),
    ("rework", "escalated"),
    ("rejected", "escalated"),
    ("working", "escalated"),
    ("review", "escalated"),
}
RUNNABLE_FROM = ("queued", "rework")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def item_dir(project, wid):
    return os.path.join(project, WORK_DIR, wid)


def _stringify_dates(node):
    """YAML round-trips an ISO timestamp back as a datetime, not a string.

    Everything downstream -- the schema, the history log, the injected context --
    treats these as strings, and a type that changes depending on whether the
    document has been through a file is the kind of bug that only appears on the
    second run. Normalising on read is cheaper than teaching every consumer to
    accept both.
    """
    import datetime as _dt
    if isinstance(node, dict):
        return {k: _stringify_dates(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_stringify_dates(v) for v in node]
    if isinstance(node, (_dt.datetime, _dt.date)):
        return node.isoformat()
    return node


def _read(path):
    if not os.path.exists(path):
        return None
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return _stringify_dates(parse_file(path))


def _schema(name):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    path = os.path.join(root, "schemas", name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate(data, schema_name):
    """Errors against the schema, or [].

    Written because the first version of this module shipped two schemas that
    nothing read. A schema no writer checks against is documentation of an
    intention, and the audit that caught it was right to call it the same defect
    this repository keeps finding elsewhere.
    """
    schema = _schema(schema_name)
    if schema is None:
        return []
    try:
        from jsonschema_mini import validate as jsvalidate
    except ImportError:
        return []
    return [str(e) for e in jsvalidate(data, schema)]


def _write_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(yaml_dumps(data))
    os.replace(tmp, path)


def load_item(project, wid):
    return _read(os.path.join(item_dir(project, wid), "work-item.yaml"))


def save_item(project, item):
    item["updated_at"] = now()
    errors = validate(item, "work-item.schema.json")
    if errors:
        raise ValueError("work item %s does not satisfy its schema: %s"
                         % (item.get("id"), "; ".join(errors[:3])))
    _write_yaml(os.path.join(item_dir(project, item["id"]), "work-item.yaml"), item)
    return item


def load_graph(project, wid):
    graph = _read(os.path.join(item_dir(project, wid), "graph.yaml"))
    return _normalise_graph(graph) if graph else graph


def _normalise_graph(graph):
    """Keys that must exist even when empty.

    The YAML emitter drops an empty list, so `depends_on: []` disappears on write
    and comes back as a missing key. Every reader then needs a `.get()` and one of
    them eventually forgets. Cheaper to make the shape stable than to make thirty
    call sites defensive.
    """
    for t in graph.get("tasks", []):
        t.setdefault("depends_on", [])
        t.setdefault("attempts", 0)
    return graph


def save_graph(project, graph):
    graph = _normalise_graph(graph)
    errors = validate(graph, "task-graph.schema.json")
    if errors:
        raise ValueError("task graph for %s does not satisfy its schema: %s"
                         % (graph.get("work_item"), "; ".join(errors[:3])))
    _write_yaml(os.path.join(item_dir(project, graph["work_item"]), "graph.yaml"), graph)
    return graph


def history(project, wid):
    path = os.path.join(item_dir(project, wid), "history.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def record(project, wid, kind, **fields):
    """Append to the item's history. Append-only on purpose.

    A history that can be edited is a record of the present. What the
    organization used to believe is evidence about how it plans, so a superseded
    generation stays rather than being tidied away.
    """
    entry = {"at": now(), "kind": kind}
    entry.update(fields)
    path = os.path.join(item_dir(project, wid), "history.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def claim(project, wid, agent_type, agent_id, session=None):
    """Bind exactly one task to exactly one running agent, and record it.

    Attribution used to be inferred from the role alone: every non-terminal task
    whose `role` matched the agent got the same result written to it. With two
    backend tasks in flight, one agent finishing one of them stamped its output
    onto both, and the graph then said work was done that nobody had done.

    A lease fixes it because the platform gives us a stable `agent_id` at
    SubagentStart and the same id at SubagentStop. One agent holds one task; a
    task already held is never offered again; and the binding is written into the
    graph, so it survives the gap between the two hook processes.

    Returns the claimed task, or None when there is nothing for this role to take.
    """
    graph = load_graph(project, wid)
    if not graph:
        return None
    held = {t.get("owner_agent") for t in graph.get("tasks", []) if t.get("owner_agent")}
    if agent_id in held:
        return resolve(project, wid, agent_id)
    for t in graph.get("tasks", []):
        if t.get("role") != agent_type or t["state"] in TERMINAL:
            continue
        if t.get("owner_agent"):
            continue
        t["owner_agent"] = agent_id
        if session:
            t["owner_session"] = session
        t["started_at"] = t.get("started_at") or now()
        t["last_activity"] = now()
        save_graph(project, graph)
        return t
    return None


def resolve(project, wid, agent_id):
    """The one task this agent holds, or None. Never a guess."""
    graph = load_graph(project, wid)
    if not graph:
        return None
    for t in graph.get("tasks", []):
        if t.get("owner_agent") == agent_id:
            return t
    return None


def release(project, wid, agent_id):
    graph = load_graph(project, wid)
    if not graph:
        return None
    for t in graph.get("tasks", []):
        if t.get("owner_agent") == agent_id:
            t.pop("owner_agent", None)
            t["last_activity"] = now()
            save_graph(project, graph)
            return t
    return None


def active_item(project, session=None, plugin_data=None):
    """Which work item this session is on.

    Session first, CURRENT second. A single project-global pointer is fine for one
    engineer in one checkout and wrong the moment there are two: session A sets it
    to FEAT-001, session B to FEAT-002, and A's next agent is briefed on B's work.
    CURRENT survives as a convenience for the single-session case; it is not the
    runtime identity.
    """
    if session and plugin_data:
        path = os.path.join(plugin_data, "state", "session-work.json")
        try:
            with open(path, encoding="utf-8") as fh:
                mapped = json.load(fh).get(session)
            if mapped:
                return mapped
        except Exception:
            pass
    return current(project)


def bind_session(plugin_data, session, wid):
    """Record which work item a session is on, outside source control.

    Runtime state does not belong in the project's history: a session id in a
    commit is noise, and two engineers would collide on it.
    """
    if not (plugin_data and session):
        return
    path = os.path.join(plugin_data, "state", "session-work.json")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        data[session] = wid
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except Exception:
        pass


def current(project):
    """The work item this session is on, or None.

    A pointer file rather than "whichever was touched last": inferring the active
    item makes the answer depend on clock skew and on whatever else happened to
    run, and a context injector that guesses wrong hands an agent someone else's
    work.
    """
    path = os.path.join(project, WORK_DIR, "CURRENT")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        wid = fh.read().strip()
    return wid or None


def set_current(project, wid):
    path = os.path.join(project, WORK_DIR, "CURRENT")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(wid + "\n")


def list_items(project):
    base = os.path.join(project, WORK_DIR)
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        if not os.path.isdir(os.path.join(base, name)):
            continue
        item = load_item(project, name)
        if item:
            out.append(item)
    return out


# ------------------------------------------------------------------ graph

def task(graph, tid):
    for t in graph.get("tasks", []):
        if t["id"] == tid:
            return t
    return None


def may_transition(frm, to):
    return to in TRANSITIONS.get(frm, ())


def path_to(frm, to):
    """The shortest legal route from one state to another, or None.

    Observation reports an outcome; it does not step a task through `assigned`
    and `working` first. Refusing "this task succeeded" because nobody logged the
    intermediate states is bookkeeping pedantry, and pedantry is what makes people
    bypass the tool. So the machine is traversed rather than demanded.

    What it still refuses is a route that does not exist: reworking an accepted
    task, or moving anything out of a terminal state. Those are real errors and
    the whole point of having a machine.
    """
    if frm == to:
        return [to]
    # A single deliberate step is always allowed: the caller named both ends.
    if to in TRANSITIONS.get(frm, ()):
        return [frm, to]
    seen, queue = {frm}, [(frm, [frm])]
    while queue:
        node, route = queue.pop(0)
        for nxt in TRANSITIONS.get(node, ()):
            if nxt in seen or (node, nxt) in DELIBERATE_ONLY:
                continue
            if nxt == to:
                return route + [nxt]
            seen.add(nxt)
            queue.append((nxt, route + [nxt]))
    return None


def dependencies_met(graph, t):
    for dep in t.get("depends_on") or []:
        d = task(graph, dep)
        if d is None or d["state"] != "accepted":
            return False
    return True


def runnable(graph):
    """Tasks whose dependencies are satisfied and whose attempts are not spent.

    Two tasks that touch the same coupled surface are never both offered: the
    coupling policy gives each surface one owner, and handing both out invites
    two agents to redefine the same contract in parallel.
    """
    out, claimed = [], set()
    for t in graph.get("tasks", []):
        if t["state"] not in RUNNABLE_FROM or not dependencies_met(graph, t):
            continue
        if t.get("attempts", 0) >= t.get("max_attempts", 3):
            continue
        if t.get("owner_agent"):
            continue
        surface = t.get("coupled_surface")
        if surface:
            if surface in claimed:
                continue
            claimed.add(surface)
        out.append(t)
    return out


def blocked_on(graph, t):
    """Which unmet dependencies are holding this task, by id."""
    return [d for d in (t.get("depends_on") or [])
            if (task(graph, d) or {}).get("state") != "accepted"]


def progress(graph):
    counts = {}
    for t in graph.get("tasks", []):
        counts[t["state"]] = counts.get(t["state"], 0) + 1
    total = len(graph.get("tasks", []))
    done = counts.get("accepted", 0)
    return {"total": total, "accepted": done, "by_state": counts,
            "complete": total > 0 and done == total}


def unreachable(graph):
    """Tasks that can never run because something they need is terminal-but-unaccepted.

    A graph where work waits on an abandoned task is a graph that looks busy and
    is finished. Nothing else notices this: every individual task is in a legal
    state.
    """
    dead = {t["id"] for t in graph.get("tasks", []) if t["state"] == "abandoned"}
    if not dead:
        return []
    stuck, changed = set(), True
    while changed:
        changed = False
        for t in graph.get("tasks", []):
            if t["id"] in dead or t["id"] in stuck or t["state"] in TERMINAL:
                continue
            if any(d in dead or d in stuck for d in (t.get("depends_on") or [])):
                stuck.add(t["id"])
                changed = True
    return sorted(stuck)
