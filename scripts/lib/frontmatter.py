"""Split YAML front matter from a markdown file."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from minyaml import parse, MinYamlError  # noqa: E402


def split(text):
    """Return (frontmatter_dict, body). Raises ValueError when malformed."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("front matter opened with '---' but never closed")
    raw = "\n".join(lines[1:end])
    try:
        data = parse(raw) if raw.strip() else {}
    except MinYamlError as exc:
        raise ValueError("front matter is not valid YAML: %s" % exc)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("front matter must be a mapping")
    return data, "\n".join(lines[end + 1:])


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return split(fh.read())
