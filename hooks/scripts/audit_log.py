#!/usr/bin/env python3
"""PostToolUse recorder. Silent by design: it never blocks and never speaks.

Records which files an agent actually changed, so that a review or an incident
can reconstruct what an agent did without replaying a transcript.

Registered on `PostToolUseFailure` as well, because the audit log's premise is
that every decision is written down and a write that was *attempted and failed*
was missing from it. The hook denials were recorded and the successes were
recorded; a tool-level failure -- the disk full, the file gone, the edit not
applying -- left nothing, so the record showed an agent that never tried. An
incident reconstructed from it would have been reading a gap as an absence of
intent. The two are distinguished by `outcome` rather than by two record types,
so anything already reading `file_change` keeps working.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import hooklib as H  # noqa: E402


def main():
    data = H.read_input()
    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path:
        sys.exit(0)
    failed = (data.get("hook_event_name") == "PostToolUseFailure")
    record = {
        "type": "file_change",
        "outcome": "failed" if failed else "applied",
        "tool": data.get("tool_name"),
        "path": path,
        "agent": data.get("agent_type"),
        "session": data.get("session_id"),
        "cwd": data.get("cwd"),
    }
    if failed:
        # Whatever the platform said went wrong, trimmed. A failure with no
        # reason is the same gap one level along.
        detail = data.get("error") or data.get("tool_response") or ""
        record["error"] = " ".join(str(detail).split())[:300]
    H.audit(record)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
