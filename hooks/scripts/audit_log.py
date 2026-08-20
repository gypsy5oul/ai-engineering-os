#!/usr/bin/env python3
"""PostToolUse recorder. Silent by design: it never blocks and never speaks.

Records which files an agent actually changed, so that a review or an incident
can reconstruct what an agent did without replaying a transcript.
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
    H.audit({
        "type": "file_change",
        "tool": data.get("tool_name"),
        "path": path,
        "agent": data.get("agent_type"),
        "session": data.get("session_id"),
        "cwd": data.get("cwd"),
    })
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
