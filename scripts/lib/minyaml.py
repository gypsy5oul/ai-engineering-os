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
import os
import copy
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


# The C loader when libyaml is installed, the Python one when it is not. Same
# grammar, same output; measured on this repository's workflows, 1.03s of parsing
# becomes 0.06s. Resolved once at import rather than per call.
try:                                                     # pragma: no cover
    import yaml as _yaml                                 # type: ignore
    _LOADER = getattr(_yaml, "CSafeLoader", None) or _yaml.SafeLoader
except ImportError:                                      # pragma: no cover
    _yaml, _LOADER = None, None

_CACHE = {}


def parse_file(path):
    """Parse a YAML file, preferring PyYAML when it is installed.

    Cached, and the cache returns a copy.

    The repository has eighteen YAML files and the pipeline parsed them 1021
    times in one run of `simulate_sdlc.py --all` alone -- 94% of that command's
    runtime was this function, and the same pattern dominated validate_plugin,
    inject_faults and run_evaluations. Nothing had changed between the calls;
    each one re-read and re-parsed a file it had already parsed.

    The copy is the part that makes caching safe. Forty-six call sites take the
    result and some of them edit it -- resolving a stage, filling in a default --
    and handing every caller the same object would let one caller's edit reach the
    next. A deepcopy costs about a twelfth of a C parse and about a hundredth of
    the pure-Python one, so correctness here is cheaper than the bug would be.

    Keyed on the file's identity and its mtime and size, so a file rewritten
    mid-process -- which the mutation tests do, on copies -- is re-read rather
    than remembered.
    """
    try:
        stat = os.stat(path)
        key = (os.path.abspath(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = None

    if key is not None and key in _CACHE:
        return copy.deepcopy(_CACHE[key])

    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if _yaml is not None:
        parsed = _yaml.load(text, Loader=_LOADER)
    else:
        parsed = parse(text)

    if key is not None:
        _CACHE[key] = parsed
        return copy.deepcopy(parsed)
    return parsed
