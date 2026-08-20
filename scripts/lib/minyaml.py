"""A deliberately small YAML subset parser.

The validators and hooks must run in CI and on an engineer's machine without
installing anything, so PyYAML cannot be a hard dependency. This parser covers
the subset the project-configuration schema uses:

    mappings, sequences, nested blocks by indentation, comments,
    quoted and bare scalars, inline [a, b] sequences, booleans, null, numbers,
    and multi-line block scalars (| and >).

Anything outside that subset raises MinYamlError rather than guessing. If a
project needs richer YAML, install PyYAML and the loader below will prefer it.
"""
import re

class MinYamlError(ValueError):
    pass


def _scalar(tok):
    t = tok.strip()
    if t == "" or t == "~" or t.lower() == "null":
        return None
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    low = t.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if re.fullmatch(r"[-+]?\d+", t):
        return int(t)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", t):
        return float(t)
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        return [_scalar(x) for x in _split_inline(inner)] if inner else []
    if t.startswith("{") and t.endswith("}"):
        inner = t[1:-1].strip()
        out = {}
        for part in _split_inline(inner):
            if ":" not in part:
                raise MinYamlError("inline mapping entry without ':': %r" % part)
            k, v = part.split(":", 1)
            out[_key(k)] = _scalar(v)
        return out
    return t


def _key(tok):
    """Mapping keys stay strings.

    YAML 1.1 would read a bare `on:` as the boolean true, which silently renames
    a legitimate configuration key. Keys are only unquoted here, never coerced.
    """
    t = tok.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    return t


def _split_inline(text):
    parts, depth, buf, quote = [], 0, [], None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _strip_comment(line):
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _tokenize(text):
    rows = []
    for n, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[:len(raw) - len(raw.lstrip())]:
            raise MinYamlError("line %d: tabs are not valid YAML indentation" % n)
        line = _strip_comment(raw)
        if not line.strip():
            continue
        rows.append((n, len(line) - len(line.lstrip(" ")), line.strip()))
    return rows


def parse(text):
    rows = _tokenize(text)
    value, idx = _parse_block(rows, 0, rows[0][1] if rows else 0)
    if idx != len(rows):
        raise MinYamlError("line %d: unexpected indentation" % rows[idx][0])
    return value


def _parse_block(rows, i, indent):
    if i >= len(rows):
        return None, i
    if rows[i][2].startswith("- "):
        return _parse_seq(rows, i, indent)
    return _parse_map(rows, i, indent)


def _parse_seq(rows, i, indent):
    items = []
    while i < len(rows) and rows[i][1] == indent and rows[i][2].startswith("- "):
        n, _, content = rows[i]
        body = content[2:].strip()
        i += 1
        if ":" in body and not body.startswith(("\"", "'")) and _looks_like_key(body):
            sub_rows = [(n, indent + 2, body)]
            while i < len(rows) and rows[i][1] > indent:
                sub_rows.append(rows[i])
                i += 1
            val, j = _parse_map(sub_rows, 0, indent + 2)
            if j != len(sub_rows):
                raise MinYamlError("line %d: could not parse sequence item" % n)
            items.append(val)
        elif body == "":
            if i < len(rows) and rows[i][1] > indent:
                val, i = _parse_block(rows, i, rows[i][1])
                items.append(val)
            else:
                items.append(None)
        else:
            items.append(_scalar(body))
    return items, i


def _looks_like_key(body):
    return bool(re.match(r"^[A-Za-z0-9_.\-]+\s*:(\s|$)", body))


def _parse_map(rows, i, indent):
    out = {}
    while i < len(rows) and rows[i][1] == indent:
        n, _, content = rows[i]
        if content.startswith("- "):
            break
        if ":" not in content:
            raise MinYamlError("line %d: expected 'key: value', got %r" % (n, content))
        key, rest = content.split(":", 1)
        key = _key(key)
        rest = rest.strip()
        i += 1
        if rest in ("|", ">", "|-", ">-"):
            block, i = _parse_literal(rows, i, indent)
            out[key] = block if rest.startswith("|") else " ".join(block.split("\n"))
        elif rest == "":
            if i < len(rows) and rows[i][1] > indent:
                val, i = _parse_block(rows, i, rows[i][1])
                out[key] = val
            else:
                out[key] = None
        else:
            out[key] = _scalar(rest)
    return out, i


def _parse_literal(rows, i, indent):
    lines = []
    while i < len(rows) and rows[i][1] > indent:
        lines.append(rows[i][2])
        i += 1
    return "\n".join(lines), i


def parse_file(path):
    """Parse a YAML file, preferring PyYAML when it is installed."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        return parse(text)
