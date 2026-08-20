"""Session-scoped record of spawns that have started and not yet finished.

A hook invocation is a separate process with no memory, so "how many agents is
this role running right now" has to be written down somewhere. This is that
somewhere: one small JSON file per session under the plugin's data directory.

The design choice worth stating is that entries **expire**. The hook cannot
reliably correlate the end of a subagent with its start, so a ledger that only
removed entries on an explicit close would leak slots, and a role that had leaked
its whole allowance could never delegate again. An expiring entry can undercount;
a leaking one eventually blocks all work. Undercounting is the safer failure for a
guardrail whose purpose is to catch runaway fan-out, not to be a semaphore.

Nothing here ever raises. A concurrency ledger that breaks a session would be a
worse problem than the one it prevents.
"""
import json
import os
import time


def _path(plugin_data, session):
    safe = "".join(c for c in (session or "nosession") if c.isalnum() or c in "-_")[:64]
    return os.path.join(plugin_data, "state", "spawns-%s.json" % (safe or "nosession"))


def _load(path, ttl):
    try:
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
    except Exception:
        return []
    if not isinstance(entries, list):
        return []
    now = time.time()
    return [e for e in entries
            if isinstance(e, dict) and (now - float(e.get("at", 0))) < ttl]


def _save(path, entries):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(entries[-200:], fh)
        os.replace(tmp, path)
    except Exception:
        pass


def open_spawns(plugin_data, session, ttl, caller=None):
    """Entries still considered running, optionally for one caller."""
    entries = _load(_path(plugin_data, session), ttl)
    if caller is None:
        return entries
    return [e for e in entries if e.get("caller") == caller]


def record(plugin_data, session, caller, target, ttl):
    path = _path(plugin_data, session)
    entries = _load(path, ttl)
    entries.append({"caller": caller, "target": target, "at": time.time()})
    _save(path, entries)


def release(plugin_data, session, ttl, caller=None, target=None):
    """Close one entry, preferring the most specific match available.

    A stop signal may name the agent that finished, or may name nothing at all.
    With no identity to go on, the oldest entry is closed: it is the one most
    likely to have finished, and the TTL covers being wrong.
    """
    path = _path(plugin_data, session)
    entries = _load(path, ttl)
    if not entries:
        return
    for match in ((caller, target), (None, target), (caller, None), (None, None)):
        c, t = match
        for i, e in enumerate(entries):
            if (c is None or e.get("caller") == c) and (t is None or e.get("target") == t):
                entries.pop(i)
                _save(path, entries)
                return
