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
import glob
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))

from frontmatter import read as read_fm  # noqa: E402
from jsonschema_mini import validate as jsvalidate, unsupported_keywords  # noqa: E402
from minyaml import parse_file  # noqa: E402

ERRORS = []
WARNINGS = []

AGENT_FM_KEYS = {"name", "description", "tools", "disallowedTools", "model",
                 "maxTurns", "skills", "memory", "background", "effort",
                 "isolation", "color", "initialPrompt"}

# Claude Code warns and ignores these on a plugin agent: "Plugin agent file <f>
# sets <k>, which is ignored for plugin agents. Use .claude/agents/ for this level
# of control." Allowing them here would let the repository carry configuration
# that looks effective and is not.
AGENT_FM_IGNORED_FOR_PLUGINS = ("permissionMode", "hooks", "mcpServers")
AGENT_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
SKILL_FM_KEYS = {"name", "description", "when_to_use", "argument-hint", "arguments",
                 "disable-model-invocation", "user-invocable", "allowed-tools", "disallowed-tools",
                 "model", "effort", "context", "agent", "background", "hooks", "paths", "shell",
                 "metadata", "license", "compatibility"}
def _model_aliases():
    """From policies/model-policy.json rather than a second copy here.

    The policy listed them and this file listed them again. They agreed today and
    nothing compared them, which is how the next model family gets added in one
    place and rejected by the other.
    """
    try:
        with open(os.path.join(ROOT, "policies", "model-policy.json"), encoding="utf-8") as fh:
            return set(json.load(fh)["aliases"])
    except Exception:
        return {"opus", "sonnet", "haiku", "fable", "inherit"}


MODEL_ALIASES = _model_aliases()
# Every section here must change what the agent does. "Skills" duplicated the
# frontmatter and "Model policy" was addressed to whoever spawns the agent, stored
# where only the agent itself would read it -- and a running subagent cannot change
# its own model. Both are in policies/agent-registry.json and the docs.
AGENT_SECTIONS = ["Role contract", "Purpose", "Responsibilities", "Not your responsibility",
                  "Authority", "Allowed actions", "Forbidden actions", "Required inputs",
                  "Expected outputs", "Escalation",
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
# Every noun the documentation counts. Hand-written numbers drifted in about
# twenty-five places, several contradicting each other inside one file, so they
# are derived from the repository and compared here.
COUNTED_NOUNS = {
    "agents": "agents", "skills": "skills", "policies": "policies",
    "workflows": "workflows", "SDLC workflows": "workflows",
    "department cycles": "department_cycles", "artifact types": "artifact_types",
    "definition-of-done predicates": "dod_predicates", "DoD predicates": "dod_predicates",
    "command rules": "command_rules", "evaluation cases": "evaluation_cases",
    "approval categories": "approval_categories",
}
COUNT_CLAIM = re.compile(r"\b(\d+)\s+(%s)\b"
                         % "|".join(sorted(COUNTED_NOUNS, key=len, reverse=True)))
VERSION_CLAIM = re.compile(r"\bVersion (\d+\.\d+\.\d+)\b")
AGENT_SET_CLAIM = re.compile(r"agent set is fixed at (\d+)")


def check_stated_counts():
    manifest_version = (load_json(".claude-plugin/plugin.json") or {}).get("version", "")
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    try:
        import repo_stats
        derived = repo_stats.stats()
    except Exception as exc:                                   # pragma: no cover
        err("scripts/repo_stats.py could not run (%r), so no stated count can be checked" % exc)
        return
    actual = {noun: derived[key] for noun, key in COUNTED_NOUNS.items() if key in derived}
    docs = [("README.md", os.path.join(ROOT, "README.md"))]
    docs_dir = os.path.join(ROOT, "docs")
    docs += [("docs/%s" % f, os.path.join(docs_dir, f))
             for f in sorted(os.listdir(docs_dir)) if f.endswith(".md")]
    for rel, path in docs:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for match in VERSION_CLAIM.finditer(text):
            stated = match.group(1)
            if stated != manifest_version:
                err("%s: says version %s; .claude-plugin/plugin.json says %s"
                    % (rel, stated, manifest_version))
        for match in AGENT_SET_CLAIM.finditer(text):
            if int(match.group(1)) != actual["agents"]:
                err("%s: says the agent set is fixed at %s; the repository has %d"
                    % (rel, match.group(1), actual["agents"]))
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


def check_skills_are_reachable():
    """A skill no agent preloads cannot be reached by any agent.

    None of the 30 agents holds the Skill tool, so the frontmatter `skills:` list
    is the only way a skill enters an agent's context. backend-development and
    frontend-development were written for the developer agents and preloaded by
    neither, while ux-designer preloaded an implementation checklist for work it
    is forbidden to do.
    """
    preloaded = set()
    agents_dir = os.path.join(ROOT, "agents")
    for name in sorted(os.listdir(agents_dir)):
        if not name.endswith(".md"):
            continue
        try:
            fm, _ = read_fm(os.path.join(agents_dir, name))
        except ValueError:
            continue
        preloaded |= set(fm.get("skills") or [])

    skills_dir = os.path.join(ROOT, "skills")
    for entry in sorted(os.listdir(skills_dir)):
        path = os.path.join(skills_dir, entry, "SKILL.md")
        if not os.path.exists(path) or entry in preloaded:
            continue
        try:
            fm, _ = read_fm(path)
        except ValueError:
            continue
        # A command-style skill is invoked by a human, so it needs no preloader.
        if fm.get("argument-hint") or fm.get("allowed-tools"):
            continue
        warn("skills/%s/: no agent preloads it and it is not a command-style skill, so no agent "
             "can reach it" % entry)


def check_workflows_can_be_abandoned():
    """A workflow with only a success exit cannot end a change that is dropped.

    Every abandoned change then leaves its department cycles open, and its
    artifacts sit in a state no predicate will ever satisfy.
    """
    base = os.path.join(ROOT, "sdlc", "workflows")
    for name in sorted(os.listdir(base)):
        if not name.endswith((".yaml", ".yml")):
            continue
        wf = parse_file(os.path.join(base, name))
        cancel = wf.get("cancellation")
        if not cancel:
            err("sdlc/workflows/%s: %s has no cancellation path, so a change that will not be "
                "finished has no way to end" % (name, wf.get("id")))
            continue
        if not cancel.get("requires"):
            err("sdlc/workflows/%s: cancellation states no requirements. Ending a change without "
                "closing its cycles leaves work the organization still believes is running." % name)


def check_agent_frontmatter_is_effective():
    """Every frontmatter key an agent sets must actually do something.

    Three keys are accepted by the parser and discarded for plugin agents. A
    repository whose whole premise is that controls are real must not carry them.
    """
    base = os.path.join(ROOT, "agents")
    for name in sorted(os.listdir(base)):
        if not name.endswith(".md"):
            continue
        rel = "agents/%s" % name
        try:
            fm, _ = read_fm(os.path.join(base, name))
        except ValueError:
            continue
        for key in AGENT_FM_IGNORED_FOR_PLUGINS:
            if key in fm:
                err("%s: sets %r, which Claude Code ignores for plugin agents. It would look "
                    "like a control and be none." % (rel, key))
        effort = fm.get("effort")
        if effort is not None and not isinstance(effort, int) and effort not in AGENT_EFFORTS:
            err("%s: effort %r is not one of %s or an integer"
                % (rel, effort, sorted(AGENT_EFFORTS)))


def check_ci_config():
    """CI is a release gate, so its own shape has to be right.

    A duplicated key in GitLab CI is silent: the loader keeps the last and the
    earlier block simply never applies. And a validation job that may fail without
    consequence is not a gate. Claude Code's own structural check must be
    mandatory on a tag; shipping a plugin its validator rejects is the one failure
    this repository cannot argue its way out of.
    """
    path = os.path.join(ROOT, ".gitlab-ci.yml")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    job, seen = None, {}
    for line in lines:
        if re.match(r"^[A-Za-z_][\w-]*:", line):
            job, seen = line.split(":")[0], {}
            continue
        m = re.match(r"^  ([a-z_]+):", line)
        if m and job:
            key = m.group(1)
            if key in seen:
                err(".gitlab-ci.yml: job %r sets %r twice. YAML keeps the last, so the earlier "
                    "block never applies." % (job, key))
            seen[key] = True

    body = "\n".join(lines)
    m = re.search(r"^claude-plugin-validate:.*?(?=^\S|\Z)", body, re.M | re.S)
    if not m:
        err(".gitlab-ci.yml: no claude-plugin-validate job. Claude Code's own structural check is "
            "the one validation this repository cannot replace.")
    elif re.search(r"^  allow_failure: true", m.group(), re.M):
        err(".gitlab-ci.yml: claude-plugin-validate allows failure unconditionally, so a release "
            "can ship a plugin Claude Code rejects. Allow it only on a branch.")


def check_permission_rules_are_effective():
    """A deny rule that matches nothing reads as protection and is none.

    Claude Code matches file permissions on Edit rules only: "Write(...) is not
    matched by file permission checks -- only Edit(path) rules are." An Edit rule
    covers every file-editing tool. The shipped templates carried three Write(...)
    deny rules for private keys and credentials that blocked nothing.
    """
    inert = {"Write": "Edit", "MultiEdit": "Edit", "NotebookEdit": "Edit", "Glob": "Read"}
    for rel in ("templates/project/settings.json",
                "templates/enterprise/managed-settings.json"):
        cfg = load_json(rel)
        if not cfg:
            continue
        perms = cfg.get("permissions") or {}
        for bucket in ("deny", "ask", "allow"):
            for rule in perms.get(bucket) or []:
                tool = str(rule).split("(")[0]
                if tool in inert and ":*" not in str(rule):
                    err("%s: %s rule %r is not matched by file permission checks. Use %s(...) "
                        "instead; it covers every file-editing tool."
                        % (rel, bucket, rule, inert[tool]))


def check_marketplace_ref_exists():
    """The marketplace ref names a tag. A tag that does not exist is a broken install.

    check_release.py compares the ref against CI_COMMIT_TAG, so it only runs *on*
    a tag and says nothing when none was ever created. This repository shipped ten
    versions with the ref pointing at tags that did not exist; every one of them
    would have failed to resolve for anyone installing from the marketplace.
    """
    manifest = load_json(".claude-plugin/plugin.json") or {}
    market = load_json(".claude-plugin/marketplace.json") or {}
    version, name = manifest.get("version"), manifest.get("name")
    if not (version and name):
        return
    try:
        out = subprocess.run(["git", "tag"], cwd=ROOT, capture_output=True, text=True,
                             timeout=30)
    except Exception:
        return
    if out.returncode != 0:
        return
    tags = set(out.stdout.split())
    if not tags:
        # A fresh clone or a repository that has never released. Nothing to check
        # against, and failing here would block the first release.
        return
    expected = "%s--v%s" % (name, version)
    for entry in market.get("plugins", []):
        ref = (entry.get("source") or {}).get("ref")
        if not ref or ref in tags:
            continue
        if ref == expected:
            # Mid-release: the version is bumped and the tag comes next. Warn rather
            # than block, because the alternative is a gate you cannot get through -
            # you would have to tag before validating, which is the wrong order.
            warn(".claude-plugin/marketplace.json: ref %r has no tag yet. Create it when you cut "
                 "the release: git tag -a %s && git push origin --tags" % (ref, ref))
        else:
            err(".claude-plugin/marketplace.json: plugin %r has ref %r, which is neither an "
                "existing tag nor the current version %s. New installs resolve to nothing."
                % (entry.get("name"), ref, expected))


def check_execution_resolution_is_live():
    """Every resolution rule the execution policy declares must exist in code.

    Same shape as the control-loop check: a policy that reads like the authority
    and is decoration. Matching is on the rule's `when`, which the resolver names
    in the reason it prints, so a rule nobody implemented shows up here rather
    than as a mode that silently never changes.
    """
    pol = load_json("policies/execution-policy.json")
    if not pol or "resolution" not in pol:
        return
    path = os.path.join(ROOT, "scripts", "resolve_execution.py")
    if not os.path.exists(path):
        err("policies/execution-policy.json declares a resolution model and "
            "scripts/resolve_execution.py does not exist, so nothing resolves anything")
        return
    with open(path, encoding="utf-8") as fh:
        code = fh.read()
    MARKERS = {
        "teams_unavailable": "teams_available(",
        "read_only_role": "role_can_write(",
        "critical_risk": "CRITICAL",
        "sibling_holds_surface": "surface_clash",
        "writes_files_and_siblings_running": "running and role_can_write",
        "declared_mode_is_available": "no fact overruled",
    }
    for rule in (pol["resolution"].get("rules") or []):
        name = rule.get("when")
        marker = MARKERS.get(name)
        if marker is None:
            err("policies/execution-policy.json: resolution rule %r is not known to "
                "check_execution_resolution_is_live, so nothing verifies it exists" % name)
        elif marker not in code:
            err("policies/execution-policy.json: resolution rule %r has no implementation in "
                "resolve_execution.py" % name)

    # A correct resolver nobody calls is the defect this repository keeps
    # producing. The policy named an enforcement path for two versions while the
    # spawn path never consulted it and the answer was never written down.
    if "def record_resolution" not in code:
        err("scripts/resolve_execution.py resolves but does not persist. Without "
            "record_resolution the answer exists only in a terminal, and the runtime "
            "cannot honour or contradict it.")
    if "W.set_execution" not in code:
        err("scripts/resolve_execution.py does not write execution.resolved onto the task")

    inject = os.path.join(ROOT, "hooks", "scripts", "inject_context.py")
    with open(inject, encoding="utf-8") as fh:
        hook = fh.read()
    # Defining a resolver and never calling it is the same defect one level in,
    # so this looks for the resolver being called by the function that claims --
    # not merely mentioned somewhere in the file.
    import ast as _ast

    def calls_in(node):
        out = set()
        for n in _ast.walk(node):
            if isinstance(n, _ast.Call):
                f = n.func
                out.add(f.id if isinstance(f, _ast.Name) else getattr(f, "attr", ""))
        return out

    claiming = [fn for fn in _ast.walk(_ast.parse(hook))
                if isinstance(fn, _ast.FunctionDef) and "claim" in calls_in(fn)]
    if not claiming:
        err("hooks/scripts/inject_context.py never calls claim(), so no task is bound to the "
            "agent being started")
    for fn in claiming:
        if not ({"resolve_and_record", "record_resolution"} & calls_in(fn)):
            err("hooks/scripts/inject_context.py: %s() claims a task without resolving its "
                "execution. The claim path is the only moment the situation is known and the "
                "spawn has not happened yet; resolving anywhere else is advice." % fn.name)

    stop = os.path.join(ROOT, "hooks", "scripts", "observe_subagent.py")
    with open(stop, encoding="utf-8") as fh:
        stop_code = fh.read()
    if "actual_execution" not in stop_code:
        err("hooks/scripts/observe_subagent.py does not record execution.actual, so nothing "
            "can tell a resolution that was honoured from one that was ignored")
    if "complete_lease" not in stop_code:
        err("hooks/scripts/observe_subagent.py does not use the atomic complete_lease, so the "
            "result write and the lease release are separate transactions and a concurrent "
            "claim between them is lost")


def telemetry_keys():
    """Every identifier telemetry.py actually emits.

    Read by running the module's own collect/derive over an empty project rather
    than by grepping, so a metric that is named in the source but never reaches
    the output cannot satisfy the check.
    """
    import tempfile
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
    try:
        import telemetry
        with tempfile.TemporaryDirectory() as d:
            counters = telemetry.collect(d)
            return set(counters) | set(telemetry.derive(counters))
    except Exception as exc:
        err("scripts/telemetry.py could not be evaluated: %r" % exc)
        return set()


def check_telemetry_policy_is_live():
    """Every metric the telemetry policy claims is computed, and every one it
    disclaims is absent.

    Both directions matter. A metric listed as measured that nothing computes is
    a claim about the organization nobody can check; a metric listed as
    unmeasured that quietly appears in the output is worse, because the reason it
    was disclaimed still applies.
    """
    pol = load_json("policies/telemetry-policy.json")
    if not pol:
        return
    path = os.path.join(ROOT, "scripts", "telemetry.py")
    if not os.path.exists(path):
        err("policies/telemetry-policy.json exists and scripts/telemetry.py does not, so "
            "nothing computes any of it")
        return
    with open(path, encoding="utf-8") as fh:
        code = fh.read()
    for name in (pol.get("not_measured") or {}):
        if '"%s"' % name in code.split("def derive(")[-1].split("def pct(")[0]:
            err("policies/telemetry-policy.json disclaims %r as unmeasured, and telemetry.py "
                "derives it anyway. The reason it was disclaimed still applies." % name)
    # The forward direction, which this used to skip entirely: it asserted three
    # hardcoded names and never read pol["measured"], so the policy could list a
    # metric nothing computes and the check still passed. Each entry now names the
    # key the tool must produce.
    produced = telemetry_keys()
    for group, entries in (pol.get("measured") or {}).items():
        for entry in entries:
            if not isinstance(entry, dict) or "key" not in entry:
                err("policies/telemetry-policy.json measured.%s lists %r without a `key`, so "
                    "nothing can check that it is computed" % (group, entry))
                continue
            if entry["key"] not in produced:
                err("policies/telemetry-policy.json claims %r (measured.%s) is computed; "
                    "telemetry.py produces no %r" % (entry["name"], group, entry["key"]))
    for signal in ("human_intervention_rate", "rework_rate", "escalation_rate"):
        if signal not in code:
            err("policies/telemetry-policy.json names %r and telemetry.py does not compute it"
                % signal)


def check_control_loop_policy_is_live():
    """Every rule the control loop policy declares must have code behind it.

    The first version of control_loop.py loaded this policy into a variable and
    then decided everything with a hardcoded chain. Four of its eight rules could
    never fire, and the bounds it declared were not the bounds in force. That is
    the `ai.agent_teams_available` shape: a file that reads like the authority and
    is decoration, which nothing catches because everything still passes.
    """
    pol = load_json("policies/control-loop-policy.json")
    if not pol:
        return
    path = os.path.join(ROOT, "scripts", "control_loop.py")
    if not os.path.exists(path):
        err("policies/control-loop-policy.json exists but scripts/control_loop.py does not, "
            "so nothing enforces it")
        return
    with open(path, encoding="utf-8") as fh:
        code = fh.read()

    declared = [r.get("when") for r in ((pol.get("decide") or {}).get("rules") or [])]
    for name in declared:
        if name and ('"%s":' % name) not in code:
            err("policies/control-loop-policy.json: rule %r has no predicate in "
                "control_loop.py RULE_PREDICATES, so it can never fire" % name)

    for loop in (pol.get("loops") or {}):
        if "max_iterations" not in (pol["loops"][loop] or {}):
            err("policies/control-loop-policy.json: loop %r declares no max_iterations. "
                "An unbounded loop is a hang." % loop)
    if "loop_bound(" not in code:
        err("scripts/control_loop.py does not read the policy's loop bounds; a limit stated "
            "in a policy and a different limit hardcoded in the code enforcing it is not a limit")

    for named in ((pol.get("enforced_by") or {}).get("mechanical") or []):
        for token in named.split():
            if token.endswith(".py") and not os.path.exists(os.path.join(ROOT, token)):
                err("policies/control-loop-policy.json claims %r enforces it, and that file "
                    "does not exist" % token)


def check_platform_capabilities():
    """Every load-bearing platform belief names the code that depends on it.

    This repository has been wrong about the platform in both directions, and
    both times the belief lived in prose with no record of how it was checked.
    A capability the code depends on has to say what depends on it, or the next
    platform refresh cannot tell which beliefs matter.
    """
    caps = load_json("policies/platform-capabilities.json")
    if not caps:
        return
    for name, cap in (caps.get("capabilities") or {}).items():
        if cap.get("evidence") not in caps.get("evidence_levels", {}) and \
                not all(part in caps.get("evidence_levels", {})
                        for part in str(cap.get("evidence", "")).split("+")):
            err("policies/platform-capabilities.json: %s has evidence %r, which is not one of %s"
                % (name, cap.get("evidence"), sorted(caps.get("evidence_levels", {}))))
        if cap.get("load_bearing") and not cap.get("used_by"):
            err("policies/platform-capabilities.json: %s is load-bearing but names nothing that "
                "uses it. A belief with no dependant cannot be re-verified meaningfully." % name)
        for token in str(cap.get("used_by", "")).split():
            if token.endswith(".py") and not os.path.exists(os.path.join(ROOT, token)):
                err("policies/platform-capabilities.json: %s says %r uses it, and that file does "
                    "not exist" % (name, token))


def check_required_fields_are_written():
    """A required field nothing produces makes the predicate reading it vacuous.

    `change` was declared in the artifact header schema and read by check_dod for
    two releases while nothing wrote it. changes_present() therefore always
    returned an empty list, the ambiguity guard could never fire, and
    `--change <id>` filtered every artifact away. The definition-of-done engine
    reported all-green on a scoping rule that was not running.

    The generic form of that mistake: a contract field with a reader and no
    writer. This checks the shipped simulator, because it is the only thing in
    the repository that produces artifacts of every type.
    """
    model = load_json("policies/artifact-model.json")
    sim = os.path.join(ROOT, "scripts", "simulate_sdlc.py")
    if not model or not os.path.exists(sim):
        return
    with open(sim, encoding="utf-8") as fh:
        code = fh.read()

    # Fields the simulator fills generically need no explicit producer; the ones
    # it deliberately refuses to invent do.
    for entry in model.get("artifact_types", []):
        for field in entry.get("required_fields", []):
            if field != "change":
                continue
            if 'field == "change"' not in code or "set_change(" not in code:
                err("policies/artifact-model.json: %s requires %r, and scripts/simulate_sdlc.py "
                    "neither sets nor stamps it. A required field nothing writes makes every "
                    "predicate that reads it vacuous." % (entry["code"], field))
            return


def check_documented_commands_parse():
    """Every `control_loop.py <sub> ...` shown in the docs is a real invocation.

    A newcomer review found the one documented `observe` example missing its
    required --item, so the single command the work-item document shows could not
    be run. The parser is asked directly rather than by running the command:
    passing --help would make argparse exit 0 no matter what is missing, and
    running it for real would write.
    """
    import shlex
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
    try:
        import control_loop
        parser = control_loop.build_parser()
    except Exception as exc:
        err("scripts/control_loop.py has no usable parser: %r" % exc)
        return

    pattern = re.compile(r"control_loop\.py\s+([a-z]+)((?:\\\n|[^\n`])*)")
    # Only inside fenced blocks. A mention in running text -- "`control_loop.py
    # open` now binds the session" -- is a reference to the subcommand, not an
    # invocation, and holding prose to argparse's required arguments is noise.
    fence = re.compile(r"^```[^\n]*\n(.*?)^```", re.M | re.S)
    seen = set()
    for rel in sorted(glob.glob(os.path.join(ROOT, "docs", "*.md"))
                      + glob.glob(os.path.join(ROOT, "*.md"))):
        with open(rel, encoding="utf-8") as fh:
            text = "\n".join(b.group(1) for b in fence.finditer(fh.read()))
        for m in pattern.finditer(text):
            sub, rest = m.group(1), m.group(2).replace("\\\n", " ")
            try:
                argv = [sub] + shlex.split(rest)
            except ValueError:
                continue
            # Placeholder arguments in prose are not invocations to check.
            if any(a.startswith("<") for a in argv):
                continue
            key = tuple(argv)
            if key in seen:
                continue
            seen.add(key)
            try:
                parser.parse_args(argv)
            except SystemExit:
                err("%s documents `control_loop.py %s`, which its own parser rejects"
                    % (os.path.relpath(rel, ROOT), " ".join(argv)))
            except Exception:
                pass


def check_docs_are_reachable():
    """Every document is listed in the README, and every listing exists.

    Thirty-one documents with no index is a pile, not documentation: a reader
    cannot tell what to read first or whether they have missed something. This
    also catches the quieter failure, a document written and never linked, which
    is how docs/lsp.md and docs/work-items.md each nearly shipped invisible.
    """
    readme = os.path.join(ROOT, "README.md")
    docs_dir = os.path.join(ROOT, "docs")
    if not (os.path.exists(readme) and os.path.isdir(docs_dir)):
        return
    with open(readme, encoding="utf-8") as fh:
        text = fh.read()
    listed = set(re.findall(r"\((?:\./)?docs/([a-z0-9-]+\.md)\)", text))
    actual = {f for f in os.listdir(docs_dir) if f.endswith(".md")}
    for missing in sorted(actual - listed):
        err("docs/%s exists and the README does not link it, so nobody will find it" % missing)
    for ghost in sorted(listed - actual):
        err("README.md links docs/%s, which does not exist" % ghost)


def check_artifact_model_matches_the_header_schema():
    """The artifact model and the header schema must agree on statuses and links.

    They drifted: the model declared seven statuses the schema rejected and
    required a link kind it forbade, so 37 of the 49 artifacts the simulation
    writes were invalid while it reported every definition of done satisfied. The
    model is the authority on what states its own types have; this check is what
    keeps the schema from falling behind it.
    """
    model = load_json("policies/artifact-model.json")
    schema = load_json("schemas/artifact-header.schema.json")
    if not (model and schema):
        return
    allowed = set((schema.get("properties", {}).get("status", {}) or {}).get("enum", []))
    link_kinds = set(((schema.get("properties", {}).get("links", {}) or {})
                      .get("properties", {})))
    for entry in model.get("artifact_types", []):
        for status in entry.get("statuses", []):
            if allowed and status not in allowed:
                err("policies/artifact-model.json: %s declares status %r, which "
                    "schemas/artifact-header.schema.json rejects. Every artifact of that type "
                    "would be invalid." % (entry["code"], status))
        for link in entry.get("links_required", []):
            if link == "source":
                continue          # a top-level header field, not a link
            if link_kinds and link not in link_kinds:
                err("policies/artifact-model.json: %s requires the link %r, which the header "
                    "schema does not declare and additionalProperties forbids."
                    % (entry["code"], link))


def check_every_predicate_is_exercised():
    """A predicate must be used by a workflow or covered by a test.

    The definition-of-done grammar is vocabulary, and not every word has to appear
    in every text -- but a word nothing uses and nothing tests is one whose
    implementation could rot silently and be reached for years later, by which
    time it is wrong.
    """
    model = load_json("policies/artifact-model.json")
    if not model:
        return
    declared = set(model.get("dod_predicates") or {})

    used = set()
    for sub in ("workflows", "cycles"):
        base = os.path.join(ROOT, "sdlc", sub)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.endswith((".yaml", ".yml")):
                continue
            doc = parse_file(os.path.join(base, name))
            entries = list(doc.get("definition_of_done") or [])
            entries += list((doc.get("acceptance") or {}).get("conditions") or [])
            for stage in doc.get("stages") or []:
                entries += list(stage.get("definition_of_done") or [])
            used |= {e.split("(")[0].strip() for e in entries}

    tested = ""
    tdir = os.path.join(ROOT, "tests")
    if os.path.isdir(tdir):
        for name in sorted(os.listdir(tdir)):
            if name.endswith(".py"):
                with open(os.path.join(tdir, name), encoding="utf-8") as fh:
                    tested += fh.read()

    for pred in sorted(declared - used):
        if pred not in tested:
            err("policies/artifact-model.json: predicate %r is used by no workflow and covered "
                "by no test, so nothing would notice if its implementation broke" % pred)


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


WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")


def cannot_write(role, storage, scope, registry):
    """Why this role could not write an artifact stored at `storage`, or None.

    Three ways it fails, and only the last was ever checked: the role holds no
    write tool, the role has no write-scope entry at all, or its scope excludes
    the path. A storage that is not a repository path -- REVIEW lives in the
    merge request -- is not a file write and is not checked.
    """
    if not storage.startswith(("docs/", "tests/", "ops/", "src/")):
        return None
    profiles = (load_json("policies/tool-permissions.json") or {}).get("profiles", {})
    entry = next((a for a in registry.get("agents", []) if a["name"] == role), None)
    if entry is None:
        return "it is not a known agent"
    tools = (profiles.get(entry.get("tool_profile")) or {}).get("tools") or []
    if not any(t in tools for t in WRITE_TOOLS):
        return ("its tool profile %r holds no write tool"
                % entry.get("tool_profile"))
    role_scope = (scope.get("roles") or {}).get(role)
    if role_scope is None:
        return "it has no entry in write-scope.json, so nothing scopes it"
    where = storage.rstrip("/")
    if role_scope.get("mode") == "allow":
        if not any(where.startswith(p.replace("/**", "").rstrip("/"))
                   for p in role_scope.get("allow", [])):
            return "its allow-mode scope does not cover that path"
    elif role_scope.get("mode") == "deny":
        if any(where.startswith(p.replace("/**", "").rstrip("/"))
               for p in role_scope.get("deny", [])):
            return "its deny list covers that path"
    return None


def check_agent_write_scope_matches_the_policy(registry):
    """The body table an agent reads must be the policy the hook enforces.

    Seven agents had drifted. Where the body was narrower the agent declined work
    it was authorized for -- sre read its own contract and concluded it could not
    write the readiness record three stages require it to produce. Where it was
    wider the agent planned edits the guard rejects. Both are the same bug: two
    copies of one fact.
    """
    sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
    from agent_render import write_scope_line
    scope = load_json("policies/write-scope.json") or {}
    profiles = (load_json("policies/tool-permissions.json") or {}).get("profiles", {})
    for a in registry.get("agents", []):
        path = os.path.join(ROOT, "agents", a["name"] + ".md")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r"^\| Write scope \| (.*?) \|$", text, re.M)
        if not m:
            err("agents/%s.md: no '| Write scope |' row" % a["name"])
            continue
        want = write_scope_line(a["name"], scope,
                                (profiles.get(a["tool_profile"]) or {}).get("tools", []))
        if m.group(1).strip() != want:
            err("agents/%s.md: write scope disagrees with policies/write-scope.json\n"
                "        file:   %s\n        policy: %s" % (a["name"], m.group(1).strip(), want))


def check_task_synthesis_is_live():
    """Every rule the synthesis policy states is enforced by the validator.

    A decomposition policy nobody checks is the most dangerous version of this
    repository's recurring defect: it reads like the rules the graph is held to,
    and a proposal violating all of them would be grafted in silently.
    """
    pol = load_json("policies/task-synthesis.json")
    if not pol:
        return
    path = os.path.join(ROOT, "scripts", "synthesize_tasks.py")
    if not os.path.exists(path):
        err("policies/task-synthesis.json exists and scripts/synthesize_tasks.py does not, so "
            "nothing decomposes anything and nothing enforces these rules")
        return
    with open(path, encoding="utf-8") as fh:
        code = fh.read()
    for rule in pol.get("rules", []):
        rid = rule.get("id")
        # Each rule id must appear in a refusal message, which is the only place
        # it can have an effect.
        if ('"%s:' % rid) not in code and ("'%s:" % rid) not in code:
            err("policies/task-synthesis.json: rule %s (%s) is stated and never enforced -- no "
                "refusal in synthesize_tasks.py cites it" % (rid, rule.get("rule")))
    for name in ("def check(", "def derive(", "def cycles("):
        if name not in code:
            err("scripts/synthesize_tasks.py is missing %s, which the policy's modes depend on"
                % name.strip("def ("))
    schema = os.path.join(ROOT, "schemas", "task-proposal.schema.json")
    if not os.path.exists(schema):
        err("policies/task-synthesis.json describes a proposed mode and "
            "schemas/task-proposal.schema.json does not exist, so a proposal is unchecked "
            "before its rules are even reached")
    else:
        model = load_json("schemas/task-proposal.schema.json") or {}
        cap = ((model.get("properties") or {}).get("children") or {}).get("maxItems")
        if cap != pol.get("max_children"):
            err("schemas/task-proposal.schema.json allows %s children and "
                "policies/task-synthesis.json permits %s. Two bounds that disagree means one of "
                "them is not the bound." % (cap, pol.get("max_children")))


def check_release_acts_have_distinct_ids():
    """Two release acts may not share an approval id.

    policies/release-authority.json says collapsing any two acts removes the
    separation of duties, and then gave release_approval and
    deployment_authorization the same AP-01. Because human_approval_recorded
    matches a policy_ref anywhere in the change, one id across two acts meant the
    content approval satisfied the authorization gate on its own -- the collapse
    the file exists to prevent, asserted by the file that prevents it.
    """
    model = load_json("policies/release-authority.json") or {}
    seen = {}
    for name, act in (model.get("acts") or {}).items():
        ref = act.get("policy_ref")
        if not ref:
            continue
        if ref in seen:
            err("policies/release-authority.json: acts %r and %r both use %s. The predicate "
                "matches an approval id anywhere in the change, so one satisfies the other."
                % (seen[ref], name, ref))
        seen[ref] = name


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
        # This checked one of the three ways it can fail, and only as a warning,
        # so DEPA shipped with an owner holding no write tools at all and a
        # workflow whose definition of done required it to produce the file.
        storage = a.get("storage", "")
        for role in [a["owner_role"]] + list(a.get("may_modify") or []):
            why = cannot_write(role, storage, scope, registry)
            if not why:
                continue
            if role == a["owner_role"]:
                err("%s: owner %s cannot write %s -- %s" % (where, role, storage, why))
            else:
                warn("%s: may_modify names %s, which cannot write %s -- %s"
                     % (where, role, storage, why))




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
    check_skills_are_reachable()
    check_agent_frontmatter_is_effective()
    check_frontmatter_is_strict_yaml()
    check_stated_counts()
    check_documented_commands_parse()
    check_docs_are_reachable()
    check_spawn_edges_are_executable()
    check_hooks()
    check_ci_config()
    check_control_loop_policy_is_live()
    check_execution_resolution_is_live()
    check_telemetry_policy_is_live()
    check_platform_capabilities()
    check_required_fields_are_written()
    check_marketplace_ref_exists()
    check_permission_rules_are_effective()
    check_schemas()
    check_workflows(registry)
    check_workflows_can_be_abandoned()
    check_approval_semantics(registry)
    check_definitions_of_done()
    check_execution_and_model(registry)
    check_artifact_model()
    check_every_predicate_is_exercised()
    check_artifact_model_matches_the_header_schema()
    check_coupling()
    check_team_requirements()
    check_agent_write_scope_matches_the_policy(registry)
    check_task_synthesis_is_live()
    check_release_acts_have_distinct_ids()
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
