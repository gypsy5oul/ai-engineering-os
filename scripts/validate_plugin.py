#!/usr/bin/env python3
"""Static validation of the ai-engineering-os plugin.

Checks structure, frontmatter, and — more importantly — that the policy
documents, the agent files and the workflows still agree with each other.
Drift between those is the failure mode this repository is most exposed to.

Exit code 0 on success, 1 on error. Warnings do not fail unless --strict.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))

from frontmatter import read as read_fm  # noqa: E402
from jsonschema_mini import validate as jsvalidate, unsupported_keywords  # noqa: E402
from minyaml import parse_file  # noqa: E402

ERRORS = []
WARNINGS = []

AGENT_FM_KEYS = {"name", "description", "tools", "disallowedTools", "model", "permissionMode",
                 "maxTurns", "skills", "mcpServers", "hooks", "memory", "background", "effort",
                 "isolation", "color", "initialPrompt"}
SKILL_FM_KEYS = {"name", "description", "when_to_use", "argument-hint", "arguments",
                 "disable-model-invocation", "user-invocable", "allowed-tools", "disallowed-tools",
                 "model", "effort", "context", "agent", "background", "hooks", "paths", "shell",
                 "metadata", "license", "compatibility"}
MODEL_ALIASES = {"opus", "sonnet", "haiku", "fable", "inherit"}
AGENT_SECTIONS = ["Role contract", "Purpose", "Responsibilities", "Not your responsibility",
                  "Authority", "Allowed actions", "Forbidden actions", "Required inputs",
                  "Expected outputs", "Skills", "Model policy", "Escalation",
                  "Review requirements", "Handoff", "Definition of done"]


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def load_json(rel):
    path = os.path.join(ROOT, rel)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        err("%s: cannot parse JSON (%s)" % (rel, exc))
        return None


# --------------------------------------------------------------------------


def check_manifest():
    manifest = load_json(".claude-plugin/plugin.json")
    if manifest is None:
        return
    if manifest.get("name") != "ai-engineering-os":
        err("plugin.json: name must be 'ai-engineering-os'")
    version = manifest.get("version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        err("plugin.json: version %r is not semantic versioning" % version)
    for field in ("description", "author", "license"):
        if not manifest.get(field):
            warn("plugin.json: '%s' is not set" % field)
    settings = manifest.get("settings")
    if settings and set(settings) - {"agent", "subagentStatusLine"}:
        err("plugin.json: 'settings' supports only 'agent' and 'subagentStatusLine'")

    for forbidden in ("agents", "skills", "hooks", "commands"):
        stray = os.path.join(ROOT, ".claude-plugin", forbidden)
        if os.path.exists(stray):
            err(".claude-plugin/%s/ must live at the plugin root, not inside .claude-plugin/" % forbidden)

    root_settings = os.path.join(ROOT, "settings.json")
    if os.path.exists(root_settings):
        data = load_json("settings.json") or {}
        if set(data) - {"agent", "subagentStatusLine"}:
            err("settings.json at the plugin root supports only 'agent' and 'subagentStatusLine'; "
                "other keys are silently ignored by Claude Code")


def check_marketplace():
    mp = load_json(".claude-plugin/marketplace.json")
    if mp is None:
        return
    for field in ("name", "owner", "plugins"):
        if field not in mp:
            err("marketplace.json: missing required field '%s'" % field)
    for entry in mp.get("plugins", []):
        if "source" not in entry:
            err("marketplace.json: plugin %r has no source" % entry.get("name"))
        src = entry.get("source")
        url = src.get("url") if isinstance(src, dict) else ""
        if isinstance(url, str) and "example.com" in url:
            warn("marketplace.json: plugin %r still points at the placeholder URL %s; set your "
                 "GitLab URL before distributing" % (entry.get("name"), url))


def check_agents(registry, profiles, write_scope):
    reg_names = {a["name"]: a for a in registry.get("agents", [])}
    files = sorted(f for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md"))
    file_names = set()

    for fname in files:
        rel = "agents/" + fname
        try:
            fm, body = read_fm(os.path.join(ROOT, rel))
        except ValueError as exc:
            err("%s: %s" % (rel, exc))
            continue
        name = fm.get("name")
        if not name:
            err("%s: frontmatter has no 'name'" % rel)
            continue
        file_names.add(name)
        if name != fname[:-3]:
            err("%s: frontmatter name %r must match the file name" % (rel, name))
        if ":" in str(name):
            err("%s: agent names cannot contain ':'" % rel)

        unknown = set(fm) - AGENT_FM_KEYS
        if unknown:
            err("%s: unsupported frontmatter keys %s" % (rel, sorted(unknown)))

        desc = fm.get("description", "")
        if len(desc) < 40:
            err("%s: description is too short to route delegation" % rel)
        if len(desc) > 1024:
            warn("%s: description is %d characters; long descriptions cost context on every session"
                 % (rel, len(desc)))

        entry = reg_names.get(name)
        if entry is None:
            err("%s: not present in policies/agent-registry.json" % rel)
            continue

        model = fm.get("model")
        if model not in MODEL_ALIASES:
            err("%s: model %r must be one of %s (dated model ids are not hard-coded here)"
                % (rel, model, sorted(MODEL_ALIASES)))
        elif model != entry["default_model"]:
            err("%s: model %r disagrees with the registry default %r"
                % (rel, model, entry["default_model"]))

        profile = profiles["profiles"].get(entry["tool_profile"])
        if profile is None:
            err("%s: registry references unknown tool profile %r" % (rel, entry["tool_profile"]))
        else:
            declared = [t.strip() for t in str(fm.get("tools", "")).split(",") if t.strip()]
            if declared != profile["tools"]:
                err("%s: tools %s do not match profile '%s' %s"
                    % (rel, declared, entry["tool_profile"], profile["tools"]))
            if entry["risk"] in ("HIGH", "CRITICAL") and "Write" in declared and \
                    entry["name"] not in write_scope.get("roles", {}):
                err("%s: HIGH/CRITICAL role has Write but no entry in policies/write-scope.json" % rel)

        for skill in fm.get("skills") or []:
            if not os.path.isdir(os.path.join(ROOT, "skills", skill)):
                err("%s: preloads skill %r which does not exist" % (rel, skill))

        headings = re.findall(r"^## (.+)$", body, re.M)
        if headings != AGENT_SECTIONS:
            missing = [s for s in AGENT_SECTIONS if s not in headings]
            extra = [s for s in headings if s not in AGENT_SECTIONS]
            err("%s: role contract sections wrong. missing=%s unexpected=%s" % (rel, missing, extra))

    for name in reg_names:
        if name not in file_names:
            err("policies/agent-registry.json: agent %r has no agents/%s.md" % (name, name))


def check_registry_consistency(registry, profiles, write_scope, routing):
    names = {a["name"] for a in registry.get("agents", [])}
    for a in registry.get("agents", []):
        for target in a["may_spawn"]:
            if target not in names:
                err("agent-registry: %s may_spawn unknown agent %r" % (a["name"], target))
            if target == a["name"]:
                err("agent-registry: %s may_spawn itself" % a["name"])
        if a["tool_profile"] not in profiles["profiles"]:
            err("agent-registry: %s has unknown tool_profile %r" % (a["name"], a["tool_profile"]))
        suite = os.path.join(ROOT, "evaluations", a["evaluation_suite"])
        if not os.path.isdir(suite):
            err("agent-registry: %s references missing evaluation suite evaluations/%s/"
                % (a["name"], a["evaluation_suite"]))
        profile = profiles["profiles"].get(a["tool_profile"], {})
        if a["risk"] == "CRITICAL" and "Write" in profile.get("tools", []):
            err("agent-registry: CRITICAL agent %s must not have write tools" % a["name"])
        if "review" in a["name"] and "Write" in profile.get("tools", []):
            err("agent-registry: reviewer %s must not have write tools; independence is structural"
                % a["name"])

    for role in write_scope.get("roles", {}):
        if role not in names:
            err("write-scope.json: unknown role %r" % role)
    for route in routing.get("routes", []):
        for reviewer in route.get("reviewers", []):
            if reviewer not in names:
                err("review-routing.json: route %s names unknown reviewer %r" % (route["id"], reviewer))
    for reviewer in routing.get("always", []):
        if reviewer not in names:
            err("review-routing.json: 'always' names unknown reviewer %r" % reviewer)


def check_skills():
    base = os.path.join(ROOT, "skills")
    for entry in sorted(os.listdir(base)):
        skill_dir = os.path.join(base, entry)
        if not os.path.isdir(skill_dir):
            continue
        path = os.path.join(skill_dir, "SKILL.md")
        rel = "skills/%s/SKILL.md" % entry
        if not os.path.exists(path):
            err("skills/%s/: no SKILL.md" % entry)
            continue
        try:
            fm, body = read_fm(path)
        except ValueError as exc:
            err("%s: %s" % (rel, exc))
            continue
        unknown = set(fm) - SKILL_FM_KEYS
        if unknown:
            err("%s: unsupported frontmatter keys %s" % (rel, sorted(unknown)))
        if fm.get("name") and fm["name"] != entry:
            err("%s: frontmatter name %r must match the directory name %r" % (rel, fm["name"], entry))
        desc = fm.get("description", "")
        if not desc:
            err("%s: no description; Claude cannot decide when to use it" % rel)
        combined = len(desc) + len(fm.get("when_to_use", "") or "")
        if combined > 1536:
            err("%s: description + when_to_use is %d characters; the listing truncates at 1536"
                % (rel, combined))
        if len(body.strip()) < 400:
            warn("%s: body is very short; is this skill carrying real guidance?" % rel)
        if fm.get("model") and fm["model"] not in MODEL_ALIASES:
            err("%s: model %r is not a supported alias" % (rel, fm["model"]))


# These two skills maintain the plugin itself, so their commands legitimately run
# with the plugin checkout as the working directory. Every other skill runs inside
# a user's project, where a bare `scripts/` path resolves to nothing.
PLUGIN_REPO_SKILLS = {"agent-development", "agent-evaluation"}

UNROOTED = re.compile(
    r"(?<!\$\{CLAUDE_PLUGIN_ROOT\}/)(?:^|[\s`\"'(])"
    r"(?:python3?\s+)?(?:\./)?((?:scripts|hooks|notification|policies|sdlc|schemas|templates)/[^\s`\"')]+)",
    re.M)
BIN_RELATIVE = re.compile(r"(?:^|[\s`\"'(])\./bin/(\w[\w-]*)", re.M)


def check_skill_paths():
    """A skill body executes with the user's project as the working directory.

    Plugin-owned files must be addressed through ${CLAUDE_PLUGIN_ROOT}, and bin/
    commands invoked bare, because bin/ is placed on PATH rather than being a
    directory the project contains.
    """
    base = os.path.join(ROOT, "skills")
    for entry in sorted(os.listdir(base)):
        path = os.path.join(base, entry, "SKILL.md")
        if entry in PLUGIN_REPO_SKILLS or not os.path.exists(path):
            continue
        rel = "skills/%s/SKILL.md" % entry
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        for match in sorted({m.group(1) for m in UNROOTED.finditer(body)}):
            err("%s: %r is a plugin path without ${CLAUDE_PLUGIN_ROOT}; "
                "it will not resolve from a project" % (rel, match))
        for match in sorted({m.group(1) for m in BIN_RELATIVE.finditer(body)}):
            err("%s: call %r bare; bin/ is on PATH, not in the project" % (rel, match))


# A plain YAML scalar containing ": " is a syntax error to any strict parser
# (js-yaml, PyYAML), even though Claude Code's own frontmatter reader tolerates it.
# Tolerated today is not portable tomorrow, so require the quotes.
COLON_IN_SCALAR = re.compile(r"(?m)^([A-Za-z][\w-]*):[ \t]+([^\"'\s].*)$")


def check_frontmatter_is_strict_yaml():
    targets = [("agents/%s" % f, os.path.join(ROOT, "agents", f))
               for f in sorted(os.listdir(os.path.join(ROOT, "agents"))) if f.endswith(".md")]
    skills_dir = os.path.join(ROOT, "skills")
    targets += [("skills/%s/SKILL.md" % d, os.path.join(skills_dir, d, "SKILL.md"))
                for d in sorted(os.listdir(skills_dir))
                if os.path.exists(os.path.join(skills_dir, d, "SKILL.md"))]
    for rel, path in targets:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if not text.startswith("---"):
            continue
        fm = text.split("---", 2)[1]
        for match in COLON_IN_SCALAR.finditer(fm):
            if ": " in match.group(2):
                err("%s: %r contains ': ' unquoted; strict YAML parsers reject this "
                    "frontmatter. Wrap the value in double quotes." % (rel, match.group(1)))


# Counts stated in prose drift silently every time a component is added. A plugin
# whose subject is consistency cannot claim five different totals across four
# documents, which is what happened before this check existed.
COUNT_CLAIM = re.compile(r"\b(\d+)\s+(agents|skills|evaluation cases)\b")


def check_stated_counts():
    actual = {
        "agents": len([f for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md")]),
        "skills": len([d for d in os.listdir(os.path.join(ROOT, "skills"))
                       if os.path.exists(os.path.join(ROOT, "skills", d, "SKILL.md"))]),
        "evaluation cases": sum(len([f for f in files if f.endswith(".json")])
                                for _, _, files in os.walk(os.path.join(ROOT, "evaluations"))),
    }
    docs = [("README.md", os.path.join(ROOT, "README.md"))]
    docs_dir = os.path.join(ROOT, "docs")
    docs += [("docs/%s" % f, os.path.join(docs_dir, f))
             for f in sorted(os.listdir(docs_dir)) if f.endswith(".md")]
    for rel, path in docs:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for match in COUNT_CLAIM.finditer(text):
            stated, noun = int(match.group(1)), match.group(2)
            # A count inside backticks is quoted output, not a claim about this repository.
            if text[:match.start()].count("`") % 2:
                continue
            if stated != actual[noun]:
                err("%s: claims %d %s; the repository has %d"
                    % (rel, stated, noun, actual[noun]))


def check_spawn_edges_are_executable():
    """A may_spawn edge is a promise the role can only keep with the Agent tool.

    Three roles carried spawn authority in the registry, advertised it in their
    bodies, and ran a tool profile without Agent. The guard would have allowed a
    delegation the role had no way to attempt, and every routed specialist review
    fell back to the main session.
    """
    registry = load_json("policies/agent-registry.json") or {}
    profiles = (load_json("policies/tool-permissions.json") or {}).get("profiles", {})
    entries = registry.get("agents") or []
    if isinstance(entries, dict):
        entries = [dict(v, name=k) for k, v in entries.items()]
    spawnable = set()
    for entry in entries:
        name = entry.get("name") or entry.get("id")
        targets = entry.get("may_spawn") or []
        if not targets:
            continue
        tools = (profiles.get(entry.get("tool_profile"), {}) or {}).get("tools", [])
        if "Agent" not in tools:
            err("policies/agent-registry.json: %r may_spawn %s but its tool profile %r has no "
                "Agent tool, so it cannot delegate at all"
                % (name, targets, entry.get("tool_profile")))
            continue
        spawnable |= set(targets)

    # Every reviewer the routing policy can require must be reachable by someone,
    # or the route is a rule no part of the organization can execute.
    routing = load_json("policies/review-routing.json") or {}
    for route in routing.get("routes", []):
        unreachable = [r for r in route.get("reviewers", []) if r not in spawnable]
        if unreachable and not route.get("notes"):
            err("policies/review-routing.json: %s routes %s, which no role may spawn. Either grant "
                "an edge or record in the route's notes why it is dispatched from the main session."
                % (route["id"], unreachable))


def check_hooks():
    cfg = load_json("hooks/hooks.json")
    if cfg is None:
        return
    events = cfg.get("hooks", {})
    if not events:
        err("hooks/hooks.json: no hooks defined")
    for event, matchers in events.items():
        for matcher in matchers:
            for hook in matcher.get("hooks", []):
                if hook.get("type") != "command":
                    continue
                command = hook.get("command", "")
                if "${CLAUDE_PLUGIN_ROOT}" not in command:
                    err("hooks.json: %s command does not use ${CLAUDE_PLUGIN_ROOT}: %r" % (event, command))
                m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"']+)", command)
                if m:
                    script = os.path.join(ROOT, m.group(1))
                    if not os.path.exists(script):
                        err("hooks.json: %s references missing script %s" % (event, m.group(1)))
                    elif not os.access(script, os.X_OK):
                        warn("hooks.json: %s script %s is not executable" % (event, m.group(1)))
                if not hook.get("timeout"):
                    warn("hooks.json: %s hook has no timeout" % event)

    pol = load_json("policies/hook-policy.json") or {}
    seen = set()
    for rule in pol.get("rules", []):
        if rule["id"] in seen:
            err("hook-policy.json: duplicate rule id %s" % rule["id"])
        seen.add(rule["id"])
        try:
            re.compile(rule["pattern"])
        except re.error as exc:
            err("hook-policy.json: rule %s has an invalid regex (%s)" % (rule["id"], exc))
        if rule["action"] not in ("deny", "escalate", "warn", "audit"):
            err("hook-policy.json: rule %s has unknown action %r" % (rule["id"], rule["action"]))
        if not rule.get("remediation"):
            err("hook-policy.json: rule %s has no remediation; a denial must say what to do instead"
                % rule["id"])


def check_schemas():
    base = os.path.join(ROOT, "schemas")
    for name in sorted(os.listdir(base)):
        if not name.endswith(".json"):
            continue
        data = load_json("schemas/" + name)
        if data is None:
            continue
        unsupported = unsupported_keywords(data)
        if unsupported:
            warn("schemas/%s: uses keywords the bundled validator ignores: %s"
                 % (name, sorted(unsupported)))


def check_workflows(registry):
    names = {a["name"] for a in registry.get("agents", [])}
    schema = load_json("schemas/sdlc-workflow.schema.json")
    base = os.path.join(ROOT, "sdlc", "workflows")
    ids = set()
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        rel = "sdlc/workflows/" + name
        try:
            data = parse_file(os.path.join(base, name))
        except Exception as exc:
            err("%s: cannot parse (%s)" % (rel, exc))
            continue
        for e in jsvalidate(data, schema):
            err("%s: %s" % (rel, e))
        if data.get("id") in ids:
            err("%s: duplicate workflow id %s" % (rel, data.get("id")))
        ids.add(data.get("id"))
        stage_ids = {s["id"] for s in data.get("stages", [])}
        for stage in data.get("stages", []):
            if stage["owner"] not in names:
                err("%s: stage %s owned by unknown agent %r" % (rel, stage["id"], stage["owner"]))
            for p in stage.get("participants", []) or []:
                if p not in names:
                    err("%s: stage %s lists unknown participant %r" % (rel, stage["id"], p))
            for s in stage.get("skills", []) or []:
                if not os.path.isdir(os.path.join(ROOT, "skills", s)):
                    err("%s: stage %s references unknown skill %r" % (rel, stage["id"], s))
            for p in stage.get("parallel_with", []) or []:
                if p not in stage_ids:
                    err("%s: stage %s parallel_with unknown stage %r" % (rel, stage["id"], p))
        for fp in data.get("failure_paths", []) or []:
            if fp["goto"] not in stage_ids:
                err("%s: failure path targets unknown stage %r" % (rel, fp["goto"]))


def check_evaluations(registry):
    schema = load_json("schemas/evaluation-case.schema.json")
    base = os.path.join(ROOT, "evaluations")
    suites = {a["evaluation_suite"] for a in registry.get("agents", [])}
    seen_ids = set()
    for suite in sorted(os.listdir(base)):
        sdir = os.path.join(base, suite)
        if not os.path.isdir(sdir):
            continue
        cases = [f for f in os.listdir(sdir) if f.endswith(".json")]
        if not cases:
            err("evaluations/%s/: no cases" % suite)
        adversarial = 0
        for cname in sorted(cases):
            rel = "evaluations/%s/%s" % (suite, cname)
            data = load_json(rel)
            if data is None:
                continue
            for e in jsvalidate(data, schema):
                err("%s: %s" % (rel, e))
            if data.get("id") in seen_ids:
                err("%s: duplicate case id %s" % (rel, data.get("id")))
            seen_ids.add(data.get("id"))
            if data.get("suite") != suite:
                err("%s: suite field %r does not match its directory" % (rel, data.get("suite")))
            if data.get("mode") == "deterministic" and not data.get("checks"):
                err("%s: deterministic case has no checks" % rel)
            if data.get("mode") == "llm-judged" and not data.get("rubric"):
                err("%s: llm-judged case has no rubric" % rel)
            if data.get("adversarial"):
                adversarial += 1
        if suite in suites and adversarial == 0:
            err("evaluations/%s/: no adversarial case; every suite must try to make its subject "
                "exceed its authority" % suite)




def check_approval_semantics(registry):
    """An agent verdict must never be able to pass as a human approval."""
    agent_names = {a["name"] for a in registry.get("agents", [])}
    approvals = {i["id"] for i in (load_json("policies/approval-policy.json") or {})
                 .get("human_approval_required", [])}
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        rel = "sdlc/workflows/" + name
        try:
            wf = parse_file(os.path.join(base, name))
        except Exception:
            continue
        for stage in wf.get("stages", []):
            ag = stage.get("agent_gate")
            hg = stage.get("human_gate")
            if ag:
                if not ag.get("purpose"):
                    err("%s: stage %s agent_gate has no purpose. A gate whose purpose is 'approve "
                        "the artifact' is an approval, which an agent may not give."
                        % (rel, stage["id"]))
                elif re.match(r"\s*(approv|sign[ -]?off|accept)\b", ag["purpose"], re.I):
                    err("%s: stage %s agent_gate purpose %r reads as an approval. State the "
                        "dimension being checked instead." % (rel, stage["id"], ag["purpose"]))
                reviewer = ag.get("reviewer", "")
                if reviewer == stage["owner"]:
                    err("%s: stage %s has an agent_gate reviewed by its own owner %r; "
                        "independence must be structural"
                        % (rel, stage["id"], reviewer))
                named = [w for w in re.split(r"[ ,]+", reviewer) if w in agent_names]
                if not named and reviewer in agent_names:
                    named = [reviewer]
                if not named and "per policies/review-routing.json" not in reviewer:
                    err("%s: stage %s agent_gate reviewer %r is not a known agent and does not "
                        "reference the routing policy" % (rel, stage["id"], reviewer))
            if hg:
                approver = hg.get("approver", "")
                if approver in agent_names:
                    err("%s: stage %s human_gate approver %r is an AGENT. A human gate is a decision "
                        "a named human takes; see policies/approval-authority.json"
                        % (rel, stage["id"], approver))
                role = hg.get("approver_role")
                if role and role in agent_names:
                    err("%s: stage %s human_gate approver_role %r is an agent name"
                        % (rel, stage["id"], role))
                if hg.get("policy_ref") and not role:
                    warn("%s: stage %s human_gate carries %s but names no approver_role, so the "
                         "approval cannot record a human identity"
                         % (rel, stage["id"], hg["policy_ref"]))
                ref = hg.get("policy_ref")
                if ref and ref not in approvals:
                    err("%s: stage %s human_gate policy_ref %s is not in policies/approval-policy.json"
                        % (rel, stage["id"], ref))
                if hg.get("recorded_in") == "in-session-escalation" and ref in ("AP-01",) \
                        and stage.get("risk") != "CRITICAL":
                    warn("%s: stage %s records an %s approval only as an in-session escalation; "
                         "that is not durable" % (rel, stage["id"], ref))
            # A stage that names an AP-nn anywhere must actually carry a human gate.
            blob = json.dumps(stage)
            for ap in re.findall(r"\bAP-[0-9]{2}\b", blob):
                if ap in approvals and not hg and "human_approval_recorded(%s)" % ap not in blob:
                    warn("%s: stage %s mentions %s but declares no human_gate"
                         % (rel, stage["id"], ap))


DOD_CALL = re.compile(r"^([a-z_]+)\(([^)]*)\)$")


def check_definitions_of_done():
    """Every DoD entry must be a known predicate with the right arity."""
    model = load_json("policies/artifact-model.json") or {}
    preds = model.get("dod_predicates", {})
    codes = {a["code"] for a in model.get("artifact_types", [])}
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        rel = "sdlc/workflows/" + name
        try:
            wf = parse_file(os.path.join(base, name))
        except Exception:
            continue
        entries = [("workflow", e) for e in wf.get("definition_of_done", [])]
        for stage in wf.get("stages", []):
            entries += [(stage["id"], e) for e in stage.get("definition_of_done", [])]
            for code in stage.get("produces", []) or []:
                if code not in codes:
                    err("%s: stage %s produces unknown artifact code %r"
                        % (rel, stage["id"], code))
        for where, entry in entries:
            m = DOD_CALL.match(entry.strip())
            if not m:
                err("%s [%s]: definition of done entry %r is not a predicate call; it cannot be "
                    "checked" % (rel, where, entry))
                continue
            fn, raw = m.group(1), m.group(2).strip()
            args = [a.strip() for a in raw.split(",")] if raw else []
            spec = preds.get(fn)
            if spec is None:
                err("%s [%s]: unknown definition-of-done predicate %r" % (rel, where, fn))
                continue
            if len(args) != len(spec["args"]):
                err("%s [%s]: predicate %s takes %d argument(s), got %d"
                    % (rel, where, fn, len(spec["args"]), len(args)))
                continue
            for i, arg in enumerate(args):
                if spec["args"][i] == "artifact_code" and arg not in codes:
                    err("%s [%s]: predicate %s references unknown artifact code %r"
                        % (rel, where, fn, arg))


def check_execution_and_model(registry):
    """Stages declare how they run and at what risk, so model routing is not guesswork."""
    modes = set((load_json("policies/execution-policy.json") or {}).get("modes", {}))
    risks = set((load_json("policies/risk-classification.json") or {}).get("classes", {}))
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        rel = "sdlc/workflows/" + name
        try:
            wf = parse_file(os.path.join(base, name))
        except Exception:
            continue
        for stage in wf.get("stages", []):
            if stage.get("execution") not in modes:
                err("%s: stage %s execution %r is not in policies/execution-policy.json"
                    % (rel, stage["id"], stage.get("execution")))
            if stage.get("risk") not in risks:
                err("%s: stage %s risk %r is not a known class" % (rel, stage["id"], stage.get("risk")))
            if stage.get("execution") == "team" and len(stage.get("participants") or []) < 2:
                err("%s: stage %s declares execution 'team' with fewer than two participants; "
                    "a team of one is a subagent with extra cost" % (rel, stage["id"]))
            if stage.get("execution") == "team":
                actions = " ".join(stage.get("actions") or []).lower()
                if "team" not in actions and "parallel" not in actions:
                    warn("%s: stage %s uses a team but its actions do not say why the parallelism "
                         "is worth the token multiplier" % (rel, stage["id"]))


def check_artifact_model():
    model = load_json("policies/artifact-model.json") or {}
    schema_codes = re.findall(r"\(([A-Z|]+)\)", 
                              (load_json("schemas/artifact-header.schema.json") or {})
                              .get("properties", {}).get("id", {}).get("pattern", ""))
    known = set(schema_codes[0].split("|")) if schema_codes else set()
    stage_ids = set()
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in os.listdir(base):
        if name.endswith((".yaml", ".yml")):
            try:
                for s in parse_file(os.path.join(base, name)).get("stages", []):
                    stage_ids.add(s["id"])
            except Exception:
                pass
    for a in model.get("artifact_types", []):
        if known and a["code"] not in known:
            err("artifact-model: code %s is not accepted by the artifact header id pattern" % a["code"])
        if a["produced_by_stage"] not in stage_ids:
            err("artifact-model: %s is produced by stage %r, which no workflow defines"
                % (a["code"], a["produced_by_stage"]))
        if not a.get("statuses"):
            err("artifact-model: %s has no status list" % a["code"])




def check_coupling():
    """Two stages that may run in parallel must not both own a shared surface."""
    coupling = load_json("policies/coupling-policy.json") or {}
    surfaces = {s["surface"] for s in coupling.get("coupled_surfaces", [])}
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        rel = "sdlc/workflows/" + name
        try:
            wf = parse_file(os.path.join(base, name))
        except Exception:
            continue
        stages = {s["id"]: s for s in wf.get("stages", [])}
        for stage in wf.get("stages", []):
            for surface in stage.get("coupled_artifacts", []) or []:
                if surface not in surfaces:
                    err("%s: stage %s declares unknown coupled surface %r"
                        % (rel, stage["id"], surface))
            for other_id in stage.get("parallel_with", []) or []:
                other = stages.get(other_id)
                if not other:
                    continue
                shared = set(stage.get("coupled_artifacts") or []) & set(other.get("coupled_artifacts") or [])
                if shared:
                    err("%s: stages %s and %s may run in parallel and both touch %s. File "
                        "disjointness is not enough; a shared surface needs one owner."
                        % (rel, stage["id"], other_id, sorted(shared)))


def check_team_requirements():
    """A team stage must say how strongly it needs a team, and what is lost without one."""
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        rel = "sdlc/workflows/" + name
        try:
            wf = parse_file(os.path.join(base, name))
        except Exception:
            continue
        for stage in wf.get("stages", []):
            if stage.get("execution") != "team":
                if stage.get("team_requirement"):
                    err("%s: stage %s declares team_requirement without execution 'team'"
                        % (rel, stage["id"]))
                continue
            level = stage.get("team_requirement")
            if not level:
                err("%s: stage %s runs as a team but does not say whether a team is REQUIRED, "
                    "PREFERRED or OPTIONAL" % (rel, stage["id"]))
                continue
            degraded = stage.get("degraded_mode")
            if not degraded:
                err("%s: stage %s has no degraded_mode. Falling back to a subagent silently would "
                    "pretend the two are equivalent." % (rel, stage["id"]))
                continue
            if level == "TEAM_REQUIRED" and degraded["fallback"] != "escalate" \
                    and not degraded.get("requires_human_acknowledgement"):
                err("%s: stage %s is TEAM_REQUIRED but falls back to %r without human "
                    "acknowledgement" % (rel, stage["id"], degraded["fallback"]))


def check_artifact_contracts(registry):
    """The artifact model is the state model. It must agree with the roles and the write scopes."""
    model = load_json("policies/artifact-model.json") or {}
    agents = {a["name"] for a in registry.get("agents", [])}
    codes = {a["code"] for a in model.get("artifact_types", [])}
    scope = load_json("policies/write-scope.json") or {}
    for a in model.get("artifact_types", []):
        where = "artifact-model %s" % a["code"]
        if a["owner_role"] not in agents:
            err("%s: owner_role %r is not a known agent" % (where, a["owner_role"]))
        for role in a.get("may_modify", []):
            if role not in agents:
                err("%s: may_modify names unknown role %r" % (where, role))
        for role in a.get("may_review", []):
            if role not in agents and "routed" not in role:
                err("%s: may_review names unknown role %r" % (where, role))
        approve = a.get("may_approve") or {}
        if approve.get("kind") == "human" and approve.get("role") in agents:
            err("%s: may_approve names the agent %r as a human approver"
                % (where, approve.get("role")))
        if approve.get("kind") not in ("human", "none"):
            err("%s: may_approve kind must be 'human' or 'none'" % where)
        for dep in a.get("depends_on", []) + a.get("consumed_by", []):
            if dep not in codes:
                err("%s: references unknown artifact code %r" % (where, dep))
        if a.get("immutable_after_creation") and a.get("may_modify"):
            err("%s: declared immutable but lists roles that may modify it" % where)
        if not a.get("required_fields"):
            err("%s: has no required_fields" % where)
        # The owner must actually be able to write where the artifact lives.
        storage = a.get("storage", "")
        role_scope = scope.get("roles", {}).get(a["owner_role"])
        if role_scope and role_scope.get("mode") == "allow" and storage.startswith("docs/"):
            allowed = role_scope.get("allow", [])
            if not any(storage.rstrip("/").startswith(p.replace("/**", "")) for p in allowed):
                warn("%s: owner %s cannot write %s under its allow-mode scope"
                     % (where, a["owner_role"], storage))




def check_department_cycles():
    """Delegate to scripts/check_cycle.py so the state-machine analysis lives in one place."""
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_cycle.py")],
                       capture_output=True, text=True, cwd=ROOT, timeout=120)
    for line in (r.stdout or "").splitlines():
        if line.startswith("ERROR "):
            err("cycle: " + line[6:])
        elif line.startswith("WARN "):
            warn("cycle: " + line[5:])




def check_notifications(registry):
    """The SDLC is the event source; the notification subsystem only consumes."""
    cat = load_json("notification/event-catalogue.json") or {}
    pol = load_json("notification/notification-policy.json") or {}
    chans = (load_json("notification/channels.json") or {}).get("channels", {})
    if not cat or not pol:
        err("notification/: catalogue or policy is missing")
        return

    schema = load_json("schemas/notification-policy.schema.json")
    if schema:
        for e in jsvalidate(pol, schema):
            err("notification/notification-policy.json: %s" % e)

    types = {e["type"]: e for e in cat.get("events", [])}
    # Every catalogue entry must name a real emitter, and every stage's emits
    # must be in the catalogue. Two directions that can drift are one direction.
    stage_emits = {}
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        try:
            wf = parse_file(os.path.join(base, name))
        except Exception:
            continue
        for s in wf.get("stages", []):
            key = "%s/%s" % (wf["id"], s["id"])
            for t in s.get("emits", []) or []:
                stage_emits.setdefault(t, []).append(key)
                if t not in types:
                    err("%s: emits %s, which is not in the event catalogue" % (key, t))

    cycles = set()
    cdir = os.path.join(ROOT, "sdlc", "cycles")
    if os.path.isdir(cdir):
        for name in os.listdir(cdir):
            if name.endswith((".yaml", ".yml")):
                try:
                    cycles.add(parse_file(os.path.join(cdir, name))["id"])
                except Exception:
                    pass

    for t, spec in types.items():
        src = spec["emitted_by"]
        if "/" in src:
            if t not in stage_emits:
                err("event-catalogue: %s claims to be emitted by %s, but that stage does not "
                    "declare it in emits" % (t, src))
            elif src not in stage_emits[t]:
                err("event-catalogue: %s says %s emits it, but the declaring stage(s) are %s"
                    % (t, src, stage_emits[t]))
        elif src.startswith("CYCLE-") and src not in cycles:
            err("event-catalogue: %s is emitted by unknown cycle %s" % (t, src))

    # Worker-level events must never be routed.
    worker = {t for t, s in types.items() if s["level"] == "worker"}
    for r in pol.get("rules", []):
        if r["event"] not in types:
            err("notification-policy: rule for unknown event %s" % r["event"])
        if r["event"] in worker and r["notify"] != "never":
            err("notification-policy: %s is worker-level but routed %r. A space that receives every "
                "keystroke stops being read." % (r["event"], r["notify"]))
        for c in [r["channel"]] + list(r.get("also_channels") or []):
            if c not in chans:
                err("notification-policy: %s routes to unknown channel %s" % (r["event"], c))
                continue
            spec = types.get(r["event"])
            accepts = chans[c].get("accepts_levels")
            extra = chans[c].get("also_accepts_events", [])
            if r["notify"] != "never" and spec and accepts and \
                    spec["level"] not in accepts and r["event"] not in extra:
                err("notification-policy: %s is %s-level but routed to '%s', which accepts %s. "
                    "Routing a lower level into a channel is what turns a space into noise."
                    % (r["event"], spec["level"], c, accepts))
        if r.get("template"):
            if not os.path.exists(os.path.join(ROOT, "notification", "templates",
                                               r["template"] + ".md")):
                err("notification-policy: %s names missing template %s"
                    % (r["event"], r["template"]))
        if r.get("recipients"):
            for role in r["recipients"]:
                if role in {a["name"] for a in registry.get("agents", [])}:
                    err("notification-policy: %s notifies %r, which is an agent. Recipients are "
                        "human roles." % (r["event"], role))

    # No webhook URL may be stored, and every channel must name its env var.
    for name, c in chans.items():
        if not c.get("webhook_env"):
            err("channels.json: %s does not name the environment variable holding its webhook" % name)
        for key, value in c.items():
            if isinstance(value, str) and ("chat.googleapis.com" in value or "hooks.slack.com" in value):
                err("channels.json: %s appears to contain a webhook URL. It is a bearer credential "
                    "and never enters this repository." % name)

    dispatcher = os.path.join(ROOT, "bin", "aieos-notify")
    if not os.path.exists(dispatcher):
        err("bin/aieos-notify is missing: formatting and sending must be separate acts")
    elif not os.access(dispatcher, os.X_OK):
        warn("bin/aieos-notify is not executable")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()

    registry = load_json("policies/agent-registry.json") or {}
    profiles = load_json("policies/tool-permissions.json") or {}
    write_scope = load_json("policies/write-scope.json") or {}
    routing = load_json("policies/review-routing.json") or {}

    reg_schema = load_json("schemas/agent-registry.schema.json")
    if reg_schema:
        for e in jsvalidate(registry, reg_schema):
            err("policies/agent-registry.json: %s" % e)

    check_manifest()
    check_marketplace()
    check_agents(registry, profiles, write_scope)
    check_registry_consistency(registry, profiles, write_scope, routing)
    check_skills()
    check_skill_paths()
    check_frontmatter_is_strict_yaml()
    check_stated_counts()
    check_spawn_edges_are_executable()
    check_hooks()
    check_schemas()
    check_workflows(registry)
    check_approval_semantics(registry)
    check_definitions_of_done()
    check_execution_and_model(registry)
    check_artifact_model()
    check_coupling()
    check_team_requirements()
    check_artifact_contracts(registry)
    check_department_cycles()
    check_notifications(registry)
    check_evaluations(registry)

    for w in WARNINGS:
        print("WARN  %s" % w)
    for e in ERRORS:
        print("ERROR %s" % e)
    print("\n%d error(s), %d warning(s)" % (len(ERRORS), len(WARNINGS)))
    if ERRORS or (args.strict and WARNINGS):
        return 1
    print("Plugin validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
