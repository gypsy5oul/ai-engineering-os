"""A small JSON Schema validator covering the subset this repository's schemas use.

Supported: type, required, properties, additionalProperties, items, enum,
pattern, minimum, maximum, minItems, maxItems, minLength, maxLength, const,
oneOf, anyOf, allOf, $ref to local #/definitions/*, patternProperties.

Unsupported keywords are ignored and reported by validate_schemas.py so a schema
author finds out rather than silently getting no validation.
"""
import re

SUPPORTED = {
    "type", "required", "properties", "additionalProperties", "items", "enum",
    "pattern", "minimum", "maximum", "minItems", "maxItems", "minLength",
    "maxLength", "const", "oneOf", "anyOf", "allOf", "$ref", "patternProperties",
    "title", "description", "$schema", "$id", "definitions", "default", "examples",
}

TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "number": (int, float), "integer": int, "null": type(None),
}


def _typeof(value, name):
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "boolean":
        return isinstance(value, bool)
    py = TYPES.get(name)
    return isinstance(value, py) if py else True


def _resolve(schema, root):
    ref = schema.get("$ref")
    if not ref:
        return schema
    if not ref.startswith("#/"):
        return schema
    node = root
    for part in ref[2:].split("/"):
        node = node.get(part, {})
    merged = dict(node)
    merged.update({k: v for k, v in schema.items() if k != "$ref"})
    return merged


def validate(instance, schema, root=None, path="$"):
    """Return a list of human-readable error strings."""
    root = root if root is not None else schema
    schema = _resolve(schema, root)
    errors = []

    if "const" in schema and instance != schema["const"]:
        errors.append("%s: expected constant %r" % (path, schema["const"]))

    t = schema.get("type")
    if t:
        names = t if isinstance(t, list) else [t]
        if not any(_typeof(instance, n) for n in names):
            errors.append("%s: expected type %s, got %s" % (path, "/".join(names), type(instance).__name__))
            return errors

    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: %r not in %r" % (path, instance, schema["enum"]))

    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append("%s: %r does not match /%s/" % (path, instance, schema["pattern"]))
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s: shorter than minLength %d" % (path, schema["minLength"]))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append("%s: longer than maxLength %d" % (path, schema["maxLength"]))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: below minimum %s" % (path, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s: above maximum %s" % (path, schema["maximum"]))

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append("%s: missing required property '%s'" % (path, key))
        props = schema.get("properties", {})
        pattern_props = schema.get("patternProperties", {})
        for key, value in instance.items():
            if key in props:
                errors += validate(value, props[key], root, "%s.%s" % (path, key))
                continue
            matched = False
            for rx, sub in pattern_props.items():
                if re.search(rx, key):
                    errors += validate(value, sub, root, "%s.%s" % (path, key))
                    matched = True
            if matched:
                continue
            if schema.get("additionalProperties") is False:
                errors.append("%s: unexpected property '%s'" % (path, key))
            elif isinstance(schema.get("additionalProperties"), dict):
                errors += validate(value, schema["additionalProperties"], root, "%s.%s" % (path, key))

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: fewer than minItems %d" % (path, schema["minItems"]))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append("%s: more than maxItems %d" % (path, schema["maxItems"]))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                errors += validate(item, item_schema, root, "%s[%d]" % (path, i))

    for key, combiner in (("allOf", "all"), ("anyOf", "any"), ("oneOf", "one")):
        subs = schema.get(key)
        if not subs:
            continue
        results = [validate(instance, s, root, path) for s in subs]
        passing = [r for r in results if not r]
        if combiner == "all":
            for r in results:
                errors += r
        elif combiner == "any" and not passing:
            errors.append("%s: does not match any of the %d allowed shapes" % (path, len(subs)))
        elif combiner == "one" and len(passing) != 1:
            errors.append("%s: must match exactly one shape, matched %d" % (path, len(passing)))

    return errors


def unsupported_keywords(schema, found=None):
    """Report schema keywords this validator ignores.

    Only descends through positions that hold schemas. Property *names* are
    data, not keywords, so the containers below are descended into by value.
    """
    found = found if found is not None else set()
    if isinstance(schema, list):
        for v in schema:
            unsupported_keywords(v, found)
        return found
    if not isinstance(schema, dict):
        return found
    for k, v in schema.items():
        if k in ("properties", "definitions", "patternProperties"):
            if isinstance(v, dict):
                for sub in v.values():
                    unsupported_keywords(sub, found)
            continue
        if k in ("items", "additionalProperties"):
            unsupported_keywords(v, found)
            continue
        if k in ("oneOf", "anyOf", "allOf"):
            unsupported_keywords(v, found)
            continue
        if k not in SUPPORTED and not k.startswith("x-"):
            found.add(k)
    return found
