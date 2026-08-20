#!/usr/bin/env python3
"""Stop hook: refuses to end a session that leaves a malformed artifact behind.

Everything else about the lifecycle -- stage order, definitions of done, the
department cycles -- is followed because the model reads it and chooses to. That
is stated honestly in docs/limitations.md, and it is why this hook exists: one
part of the contract can be enforced rather than requested.

The part chosen is the one that needs no session state to check. An artifact
header either satisfies schemas/artifact-header.schema.json or it does not, and
the audit log already records which files this session wrote. No stage marker,
no correlation id, nothing the model has to maintain truthfully.

Blocking is deliberately narrow. A hook that blocks on judgement would be a hook
that argues with the session; this one blocks only on a structural fact.
"""
import json
import os
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, LIB)
import hooklib as H  # noqa: E402

sys.path.insert(0, os.path.join(H.PLUGIN_ROOT, "scripts", "lib"))


def session_writes(session_id):
    """Paths this session wrote, newest first, from the audit log."""
    if not session_id:
        return []
    path = os.path.join(H.audit_dir(), __import__("time").strftime("%Y-%m") + ".jsonl")
    if not os.path.exists(path):
        return []
    seen, out = set(), []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("type") != "file_change" or rec.get("session") != session_id:
                    continue
                p = rec.get("path") or ""
                if p.endswith(".md") and p not in seen:
                    seen.add(p)
                    out.append(p)
    except Exception:
        return []
    return out


def problems(paths):
    """Structural faults in artifacts this session wrote. Never raises."""
    from frontmatter import read as read_fm
    from jsonschema_mini import validate as jsvalidate

    schema_path = os.path.join(H.PLUGIN_ROOT, "schemas", "artifact-header.schema.json")
    try:
        with open(schema_path, encoding="utf-8") as fh:
            schema = json.load(fh)
    except Exception:
        return []

    found = []
    for path in paths:
        if not os.path.isabs(path):
            path = os.path.join(H.PROJECT_DIR, path)
        if not os.path.exists(path):
            continue
        try:
            fm, _ = read_fm(path)
        except Exception:
            continue
        # Only files that are trying to be artifacts. A README is not one.
        if not isinstance(fm, dict) or not fm.get("id") or not fm.get("type"):
            continue
        errors = list(jsvalidate(fm, schema))
        if errors:
            rel = os.path.relpath(path, H.PROJECT_DIR)
            found.append("%s: %s" % (rel, "; ".join(str(e) for e in errors[:3])))
    return found


def release_slot(data):
    """Free the concurrency slot this piece of work was holding.

    Whether the stop signal names the agent that finished is not guaranteed, so
    the ledger falls back to closing the oldest entry, and expires entries anyway.
    A slot that leaks would eventually stop a role delegating at all.
    """
    try:
        import ledger
        policy = H.policy("concurrency-policy.json")
        ttl = (policy.get("ledger") or {}).get("entry_ttl_seconds", 1800)
        target = (data.get("agent_type") or "").split(":")[-1] or None
        ledger.release(H.plugin_data_dir(), data.get("session_id"), ttl, target=target)
    except Exception:
        pass


def main():
    data = H.read_input()
    if data.get("hook_event_name") == "SubagentStop" or data.get("agent_type"):
        release_slot(data)
    # Claude Code sets this when the session is already being held open by a stop
    # hook. Ignoring it is how a hook becomes an infinite loop.
    if data.get("stop_hook_active"):
        sys.exit(0)

    faults = problems(session_writes(data.get("session_id")))
    if not faults:
        sys.exit(0)

    H.audit({"type": "stop_blocked", "reason": "invalid_artifact_header", "count": len(faults)})
    sys.stdout.write(json.dumps({
        "decision": "block",
        "reason": ("This session wrote %d artifact(s) whose header does not satisfy "
                   "schemas/artifact-header.schema.json. An artifact that cannot be parsed is "
                   "invisible to every definition-of-done predicate, so the work does not count "
                   "as done. Fix these, then finish:\n  - %s"
                   % (len(faults), "\n  - ".join(faults))),
    }))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A broken gate must never trap a session. Failing open is correct here:
        # this hook adds a check, it is not a safety boundary.
        sys.exit(0)
