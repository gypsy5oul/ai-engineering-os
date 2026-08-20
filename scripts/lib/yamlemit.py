"""Minimal block-YAML emitter matching the subset scripts/lib/minyaml.py parses.

Round-trips through minyaml by construction, which is asserted in tests. Kept
deliberately small: the workflows are the only thing generated, and a general
emitter would be a second parser to keep in step with the first.
"""

def _needs_quote(s):
    if s == "" or s != s.strip():
        return True
    if s[0] in "-?:,[]{}#&*!|>'\"%@`":
        return True
    if ": " in s or s.endswith(":") or " #" in s:
        return True
    if s.lower() in ("true", "false", "yes", "no", "on", "off", "null", "~"):
        return True
    try:
        float(s)
        return True
    except ValueError:
        pass
    return False


def scalar(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if _needs_quote(s):
        return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')
    return s


def dump(value, indent=0):
    pad = " " * indent
    out = []
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, dict) and v:
                out.append("%s%s:" % (pad, k))
                out.append(dump(v, indent + 2))
            elif isinstance(v, list) and v:
                out.append("%s%s:" % (pad, k))
                out.append(dump(v, indent + 2))
            elif isinstance(v, (dict, list)):
                continue  # empty collections are omitted rather than emitted as null
            else:
                out.append("%s%s: %s" % (pad, k, scalar(v)))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                lines = dump(item, indent + 2).split("\n")
                first = lines[0][indent + 2:]
                out.append("%s- %s" % (pad, first))
                out.extend(lines[1:])
            else:
                out.append("%s- %s" % (pad, scalar(item)))
    else:
        out.append("%s%s" % (pad, scalar(value)))
    return "\n".join(x for x in out if x != "")


def dump_document(doc, header_comment=""):
    text = dump(doc)
    if header_comment:
        lines = ["# " + l if l else "#" for l in header_comment.strip().split("\n")]
        text = "\n".join(lines) + "\n\n" + text
    return text + "\n"
