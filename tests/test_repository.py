"""Repository-level tests: the validators pass, and the invariants that make the
organization coherent hold. These are the checks CI relies on."""
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
from frontmatter import read as read_fm  # noqa: E402


def script(name, *args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", name)] + list(args),
                          capture_output=True, text=True, cwd=ROOT, timeout=300)


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


class TestValidators(unittest.TestCase):
    def test_plugin_validation_passes(self):
        r = script("validate_plugin.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_schema_validation_passes(self):
        r = script("validate_schemas.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_secret_scan_clean(self):
        r = script("secret_scan.py", ROOT)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_shipped_project_template_validates(self):
        r = script("validate_project_config.py", os.path.join(ROOT, "templates/project/project.yaml"))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_deterministic_evaluations_pass(self):
        r = script("run_evaluations.py")
        self.assertEqual(r.returncode, 0, r.stdout)


class TestOrganizationalInvariants(unittest.TestCase):
    def setUp(self):
        self.registry = load("policies/agent-registry.json")
        self.profiles = load("policies/tool-permissions.json")["profiles"]
        self.agents = {a["name"]: a for a in self.registry["agents"]}

    def tools(self, name):
        return self.profiles[self.agents[name]["tool_profile"]]["tools"]

    def test_reviewers_cannot_write(self):
        for name in self.agents:
            if "review" in name:
                self.assertNotIn("Write", self.tools(name))
                self.assertNotIn("Edit", self.tools(name))

    def test_critical_agents_cannot_write(self):
        for name, agent in self.agents.items():
            if agent["risk"] == "CRITICAL":
                self.assertNotIn("Write", self.tools(name), name)

    def test_no_dated_model_identifiers(self):
        for agent in self.registry["agents"]:
            for field in ("default_model", "escalation_model"):
                self.assertIn(agent[field], {"opus", "sonnet", "haiku", "fable", "inherit"})

    def test_high_risk_roles_are_not_below_their_model_floor(self):
        floors = {c: v["implies"]["model_floor"]
                  for c, v in load("policies/risk-classification.json")["classes"].items()}
        rank = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 1, "inherit": 1}
        for agent in self.registry["agents"]:
            floor = floors[agent["risk"]]
            self.assertGreaterEqual(rank[agent["default_model"]], rank[floor],
                                    "%s runs %s below the %s floor %s"
                                    % (agent["name"], agent["default_model"], agent["risk"], floor))

    def test_every_agent_file_declares_its_forbidden_actions(self):
        for name in self.agents:
            _, body = read_fm(os.path.join(ROOT, "agents", name + ".md"))
            section = re.search(r"## Forbidden actions\n\n(.*?)\n\n## ", body, re.S)
            self.assertIsNotNone(section, "%s has no forbidden actions section" % name)
            self.assertGreaterEqual(len(section.group(1).strip().splitlines()), 1, name)

    def test_approval_policy_ids_are_referenced_by_something(self):
        policy = load("policies/approval-policy.json")
        corpus = ""
        for folder in ("agents", "skills", "sdlc", "policies", "docs", "hooks"):
            for dirpath, _, files in os.walk(os.path.join(ROOT, folder)):
                for f in files:
                    if f.endswith((".md", ".json", ".yaml", ".py")):
                        with open(os.path.join(dirpath, f), encoding="utf-8", errors="ignore") as fh:
                            corpus += fh.read()
        for item in policy["human_approval_required"]:
            self.assertIn(item["id"], corpus,
                          "%s (%s) is defined but never referenced anywhere" % (item["id"], item["category"]))

    def test_every_workflow_stage_owner_can_do_its_outputs(self):
        """A stage whose outputs are artifacts needs an owner that can write."""
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        base = os.path.join(ROOT, "sdlc", "workflows")
        for name in os.listdir(base):
            if not name.endswith(".yaml"):
                continue
            wf = parse_file(os.path.join(base, name))
            for stage in wf["stages"]:
                if stage.get("artifacts"):
                    tools = self.tools(stage["owner"])
                    self.assertIn("Write", tools,
                                  "%s stage %s produces artifacts but owner %s cannot write"
                                  % (name, stage["id"], stage["owner"]))


class TestWorkflowContracts(unittest.TestCase):
    """The v2 stage contract: entry criteria, artifacts, DoD, gates, execution."""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        base = os.path.join(ROOT, "sdlc", "workflows")
        self.workflows = {}
        for name in sorted(os.listdir(base)):
            if name.endswith((".yaml", ".yml")):
                wf = parse_file(os.path.join(base, name))
                self.workflows[wf["id"]] = wf
        self.agents = {a["name"] for a in load("policies/agent-registry.json")["agents"]}

    def test_every_stage_declares_entry_criteria_and_dod(self):
        for wid, wf in self.workflows.items():
            for s in wf["stages"]:
                with self.subTest(stage="%s/%s" % (wid, s["id"])):
                    self.assertTrue(s.get("entry_criteria"), "no entry criteria")
                    self.assertTrue(s.get("definition_of_done"), "no definition of done")
                    self.assertIn(s.get("risk"), ("LOW", "MEDIUM", "HIGH", "CRITICAL"))
                    self.assertIn(s.get("execution"), ("inline", "subagent", "team"))

    def test_no_human_gate_is_approved_by_an_agent(self):
        for wid, wf in self.workflows.items():
            for s in wf["stages"]:
                hg = s.get("human_gate")
                if hg:
                    self.assertNotIn(hg["approver"], self.agents,
                                     "%s/%s: %s is an agent" % (wid, s["id"], hg["approver"]))

    def test_no_stage_reviews_its_own_output(self):
        for wid, wf in self.workflows.items():
            for s in wf["stages"]:
                ag = s.get("agent_gate")
                if ag:
                    self.assertNotEqual(ag["reviewer"], s["owner"], "%s/%s" % (wid, s["id"]))

    def test_every_human_gate_names_where_the_decision_is_recorded(self):
        """A decision that lives only in a transcript did not happen."""
        for wid, wf in self.workflows.items():
            for s in wf["stages"]:
                hg = s.get("human_gate")
                if hg:
                    self.assertTrue(hg.get("recorded_in"), "%s/%s" % (wid, s["id"]))

    def test_team_stages_have_enough_participants_to_be_a_team(self):
        for wid, wf in self.workflows.items():
            for s in wf["stages"]:
                if s.get("execution") == "team":
                    self.assertGreaterEqual(len(s.get("participants") or []), 2,
                                            "%s/%s" % (wid, s["id"]))

    def test_definition_of_done_grammar(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_dod.py"), "--grammar"],
                           capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_every_produced_artifact_code_is_in_the_model(self):
        codes = {a["code"] for a in load("policies/artifact-model.json")["artifact_types"]}
        for wid, wf in self.workflows.items():
            for s in wf["stages"]:
                for code in s.get("produces") or []:
                    self.assertIn(code, codes, "%s/%s produces %s" % (wid, s["id"], code))

    def test_model_resolution_is_executable_for_every_stage(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "resolve_model.py"),
                            "--all", "--json"], capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = json.loads(r.stdout)
        self.assertEqual(len(rows), sum(len(w["stages"]) for w in self.workflows.values()))
        for row in rows:
            self.assertIn(row["model"], {"opus", "sonnet", "haiku", "fable", "inherit"})

    def test_project_override_cannot_drop_below_the_risk_floor(self):
        import tempfile
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from resolve_model import resolve
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, ".ai-engineering"))
        with open(os.path.join(d, ".ai-engineering", "project.json"), "w") as fh:
            json.dump({"ai": {"model_overrides": {"security-reviewer": {"model": "haiku"}}}}, fh)
        result = resolve("security-reviewer", "HIGH", "complex", project=d)
        self.assertEqual(result["model"], "opus")
        self.assertTrue(any("REFUSED" in t for t in result["trace"]))

    def test_agent_teams_are_not_a_system_of_record(self):
        sor = load("policies/system-of-record.json")
        self.assertEqual(sor["execution_mechanisms"]["agent_team_task_list"]["authoritative_for"], [])
        self.assertEqual(sor["execution_mechanisms"]["session_transcript"]["authoritative_for"], [])


class TestArtifactContracts(unittest.TestCase):
    """The artifact model is the state model. It must agree with roles and scopes."""

    def setUp(self):
        self.model = load("policies/artifact-model.json")
        self.agents = {a["name"] for a in load("policies/agent-registry.json")["agents"]}
        self.codes = {a["code"] for a in self.model["artifact_types"]}

    def test_every_type_has_a_complete_contract(self):
        required = ("code", "type", "owner_role", "produced_by_stage", "storage", "statuses",
                    "required_fields", "may_modify", "may_review", "may_approve",
                    "depends_on", "consumed_by")
        for a in self.model["artifact_types"]:
            with self.subTest(code=a["code"]):
                for field in required:
                    self.assertIn(field, a)
                self.assertIn(a["owner_role"], self.agents)

    def test_no_agent_is_named_as_a_human_approver(self):
        for a in self.model["artifact_types"]:
            approve = a.get("may_approve") or {}
            if approve.get("kind") == "human":
                self.assertNotIn(approve.get("role"), self.agents,
                                 "%s: %s is an agent" % (a["code"], approve.get("role")))

    def test_immutable_artifacts_have_no_modifiers(self):
        for a in self.model["artifact_types"]:
            if a.get("immutable_after_creation"):
                self.assertEqual(a["may_modify"], [], a["code"])

    def test_evidence_is_immutable_and_incident_is_append_only(self):
        by = {a["code"]: a for a in self.model["artifact_types"]}
        self.assertTrue(by["EVID"]["immutable_after_creation"])
        self.assertEqual(by["EVID"]["may_modify"], [])
        self.assertTrue(by["INC"].get("append_only"))

    def test_dependency_graph_is_closed(self):
        for a in self.model["artifact_types"]:
            for dep in a["depends_on"] + a["consumed_by"]:
                self.assertIn(dep, self.codes, "%s -> %s" % (a["code"], dep))

    def test_every_code_is_accepted_by_the_header_schema(self):
        import re as _re
        pattern = load("schemas/artifact-header.schema.json")["properties"]["id"]["pattern"]
        for code in self.codes:
            self.assertTrue(_re.match(pattern, "PROJ-%s-001" % code), code)

    def test_open_decision_and_evidence_exist_as_first_class_types(self):
        self.assertIn("DEC", self.codes)
        self.assertIn("EVID", self.codes)


class TestReleaseAuthority(unittest.TestCase):
    def test_three_acts_are_distinct(self):
        auth = load("policies/release-authority.json")
        for act in ("release_approval", "deployment_authorization", "deployment_execution",
                    "verification"):
            self.assertIn(act, auth["acts"])
        self.assertIn("authorized", auth["state_machine"]["approved"])
        self.assertNotIn("done", auth["state_machine"]["approved"],
                         "an approved release must not go straight to done")

    def test_both_deploying_workflows_have_an_authorize_stage(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        base = os.path.join(ROOT, "sdlc", "workflows")
        found = []
        for name in os.listdir(base):
            if not name.endswith(".yaml"):
                continue
            wf = parse_file(os.path.join(base, name))
            ids = [s["id"] for s in wf["stages"]]
            if "DEPLOY" in ids:
                self.assertIn("AUTHORIZE", ids, wf["id"])
                self.assertLess(ids.index("AUTHORIZE"), ids.index("DEPLOY"), wf["id"])
                found.append(wf["id"])
        self.assertGreaterEqual(len(found), 2, found)


class TestCoupling(unittest.TestCase):
    def test_parallel_stages_do_not_share_a_surface(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        known = {s["surface"] for s in load("policies/coupling-policy.json")["coupled_surfaces"]}
        base = os.path.join(ROOT, "sdlc", "workflows")
        for name in sorted(os.listdir(base)):
            if not name.endswith(".yaml"):
                continue
            wf = parse_file(os.path.join(base, name))
            stages = {s["id"]: s for s in wf["stages"]}
            for s in wf["stages"]:
                for surface in s.get("coupled_artifacts") or []:
                    self.assertIn(surface, known, "%s/%s" % (wf["id"], s["id"]))
                for other in s.get("parallel_with") or []:
                    shared = set(s.get("coupled_artifacts") or []) & set(
                        (stages.get(other) or {}).get("coupled_artifacts") or [])
                    self.assertEqual(shared, set(), "%s: %s || %s" % (wf["id"], s["id"], other))

    def test_every_surface_has_exactly_one_owner(self):
        agents = {a["name"] for a in load("policies/agent-registry.json")["agents"]}
        for s in load("policies/coupling-policy.json")["coupled_surfaces"]:
            self.assertIn(s["owner_role"], agents, s["surface"])


class TestTeamRequirement(unittest.TestCase):
    def test_team_stages_declare_requirement_and_degraded_mode(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        base = os.path.join(ROOT, "sdlc", "workflows")
        for name in sorted(os.listdir(base)):
            if not name.endswith(".yaml"):
                continue
            wf = parse_file(os.path.join(base, name))
            for s in wf["stages"]:
                if s.get("execution") != "team":
                    continue
                with self.subTest(stage="%s/%s" % (wf["id"], s["id"])):
                    self.assertIn(s.get("team_requirement"),
                                  ("TEAM_REQUIRED", "TEAM_PREFERRED", "TEAM_OPTIONAL"))
                    degraded = s.get("degraded_mode")
                    self.assertIsNotNone(degraded, "no degraded_mode: silence pretends equivalence")
                    self.assertTrue(degraded["guarantees_lost"])
                    if s["team_requirement"] == "TEAM_REQUIRED":
                        self.assertTrue(degraded["fallback"] == "ask"
                                        or degraded.get("requires_human_acknowledgement"))

    def test_incident_investigation_is_team_required(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        wf = parse_file(os.path.join(ROOT, "sdlc", "workflows", "incident-response.yaml"))
        stage = next(s for s in wf["stages"] if s["id"] == "INVESTIGATE")
        self.assertEqual(stage["team_requirement"], "TEAM_REQUIRED")


class TestDepartmentCycles(unittest.TestCase):
    """Level 2: the delegation, review and rework loop inside each department."""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        base = os.path.join(ROOT, "sdlc", "cycles")
        self.cycles = {}
        for name in sorted(os.listdir(base)):
            if name.endswith((".yaml", ".yml")):
                c = parse_file(os.path.join(base, name))
                self.cycles[c["id"]] = c
        self.agents = {a["name"]: a for a in load("policies/agent-registry.json")["agents"]}
        self.profiles = load("policies/tool-permissions.json")["profiles"]

    def test_checker_passes(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_cycle.py")],
                           capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_every_department_has_a_cycle(self):
        departments = {c["department"] for c in self.cycles.values()}
        for expected in ("engineering", "qa", "security", "architecture", "product",
                         "platform", "sre"):
            self.assertIn(expected, departments)

    def test_the_peer_reviewer_is_never_the_worker(self):
        for cid, c in self.cycles.items():
            peer = c["positions"]["peer_reviewer"]
            if peer == "mutual":
                self.assertGreaterEqual(len(c["positions"]["workers"]), 2,
                                        "%s: mutual review needs two workers" % cid)
            else:
                self.assertNotIn(peer, c["positions"]["workers"], cid)

    def test_the_peer_reviewer_cannot_write_the_artifact_it_reviews(self):
        scope = load("policies/write-scope.json")
        model = {a["code"]: a for a in load("policies/artifact-model.json")["artifact_types"]}
        for cid, c in self.cycles.items():
            peer = c["positions"]["peer_reviewer"]
            if peer == "mutual":
                continue
            storage = model[c["work_item"]["artifact"]]["storage"].rstrip("/")
            entry = scope["roles"].get(peer)
            if entry is None:
                continue
            if entry["mode"] == "allow":
                writable = any(storage.startswith(p.replace("/**", "").rstrip("/"))
                               for p in entry["allow"])
                self.assertFalse(writable, "%s: %s can write %s" % (cid, peer, storage))

    def test_a_head_is_never_reviewing_line_level_work(self):
        """The head receives a rollup and nothing else."""
        for cid, c in self.cycles.items():
            head = c["positions"]["head"]
            self.assertEqual(head.get("receives", "rollup"), "rollup", cid)
            self.assertNotIn(head.get("role"), c["positions"]["workers"], cid)

    def test_departments_are_managed_by_agents(self):
        """A human head puts a person in every departmental rollup, which is not
        an autonomous organization. Exactly one exception is argued: security."""
        human_headed = []
        for cid, c in self.cycles.items():
            head = c["positions"]["head"]
            if head["kind"] == "human":
                human_headed.append(cid)
                self.assertTrue(head.get("human_exception_reason"),
                                "%s: human head with no argued exception" % cid)
                continue
            entry = self.agents[head["role"]]
            self.assertIn(entry["tool_profile"], ("lead", "orchestrator"), cid)
        self.assertEqual(human_headed, ["CYCLE-SEC"],
                         "only security should be human-headed, got %s" % human_headed)

    def test_a_head_can_delegate_to_its_own_lead(self):
        for cid, c in self.cycles.items():
            head, lead = c["positions"]["head"], c["positions"]["lead"]
            if head["kind"] != "agent" or head["role"] == lead:
                continue
            self.assertIn(lead, self.agents[head["role"]]["may_spawn"],
                          "%s: head %s cannot spawn lead %s" % (cid, head["role"], lead))

    def test_the_human_owner_governs_and_does_not_operate(self):
        for cid, c in self.cycles.items():
            owner = c["positions"]["human_owner"]
            self.assertNotIn(owner["role"], self.agents, "%s: human_owner is an agent" % cid)
            self.assertTrue(owner["authority"],
                            "%s: a governance role that decides nothing specific decides "
                            "everything by default" % cid)
            self.assertEqual(owner.get("receives", "escalations-and-approvals"),
                             "escalations-and-approvals", cid)
            operational = [c["positions"]["lead"], c["positions"]["peer_reviewer"]] + \
                c["positions"]["workers"]
            self.assertNotIn(owner["role"], operational, cid)

    def test_escalation_reaches_the_human_last(self):
        for cid, c in self.cycles.items():
            order = c["escalation"]["order"]
            self.assertEqual(order[0], "worker", cid)
            self.assertEqual(order[-1], "human_owner", cid)
            self.assertLess(order.index("lead"), order.index("head"), cid)
            self.assertLess(order.index("head"), order.index("human_owner"), cid)

    def test_incident_investigation_is_unconditionally_team_required(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        wf = parse_file(os.path.join(ROOT, "sdlc", "workflows", "incident-response.yaml"))
        s = next(x for x in wf["stages"] if x["id"] == "INVESTIGATE")
        self.assertEqual(s["team_requirement"], "TEAM_REQUIRED")
        d = s["degraded_mode"]
        self.assertTrue(d["fallback"] == "ask" or d.get("requires_human_acknowledgement"))
        self.assertGreaterEqual(len(d["guarantees_lost"]), 3)

    def test_reviews_can_request_changes(self):
        """A review that can only pass is not a review."""
        for cid, c in self.cycles.items():
            for review in ("PEER_REVIEW", "LEAD_REVIEW"):
                targets = set((c["transitions"].get(review) or {}).values())
                self.assertIn("CHANGES_REQUESTED", targets, "%s/%s" % (cid, review))

    def test_rework_is_bounded(self):
        for cid, c in self.cycles.items():
            self.assertGreaterEqual(c["rework"]["limit"], 1, cid)
            self.assertLessEqual(c["rework"]["limit"], 5, cid)
            self.assertTrue(c["rework"]["on_limit"], cid)

    def test_the_rollup_is_produced_by_the_lead(self):
        for cid, c in self.cycles.items():
            self.assertEqual(c["rollup"]["produced_by"], c["positions"]["lead"], cid)

    def test_qa_validates_a_defect_before_it_becomes_a_development_item(self):
        qa = self.cycles["CYCLE-QA"]
        triage = next(s for s in qa["sub_cycles"] if s["id"] == "SUB-QA-TRIAGE")
        self.assertEqual(triage["owner"], "qa-lead")
        self.assertGreaterEqual(len(triage["questions"]), 4)
        for outcome in ("not-a-defect", "test-defect", "environment-defect", "product-defect"):
            self.assertIn(outcome, triage["outcomes"])

    def test_only_completing_stages_require_the_cycle_to_be_accepted(self):
        """A department whose work spans several stages has not finished at the
        first of them. Only the completing stage carries the predicates."""
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file
        base = os.path.join(ROOT, "sdlc", "workflows")
        wired = 0
        completing = {}
        for name in sorted(os.listdir(base)):
            if not name.endswith(".yaml"):
                continue
            wf = parse_file(os.path.join(base, name))
            for s in wf["stages"]:
                cid = s.get("department_cycle")
                if not cid:
                    continue
                wired += 1
                self.assertIn(cid, self.cycles, "%s/%s" % (wf["id"], s["id"]))
                role = s.get("cycle_role")
                self.assertIn(role, ("enters", "continues", "completes"),
                              "%s/%s" % (wf["id"], s["id"]))
                dod = s["definition_of_done"]
                preds = ("cycle_accepted(%s)" % cid, "cycle_rollup_reported(%s)" % cid,
                         "no_open_rework(%s)" % cid)
                if role == "completes":
                    completing.setdefault((wf["id"], cid), []).append(s["id"])
                    for pred in preds:
                        self.assertIn(pred, dod, "%s/%s" % (wf["id"], s["id"]))
                else:
                    for pred in preds:
                        self.assertNotIn(pred, dod,
                                         "%s/%s has role %s but requires %s"
                                         % (wf["id"], s["id"], role, pred))
        self.assertGreater(wired, 10, "only %d stages run a department cycle" % wired)
        for key, stages in completing.items():
            self.assertEqual(len(stages), 1,
                             "%s is completed at more than one stage: %s" % (key, stages))

    def test_no_two_cycles_claim_the_same_stage(self):
        claims = {}
        for cid, c in self.cycles.items():
            for ref in c["used_by_stages"]:
                self.assertNotIn(ref, claims,
                                 "%s and %s both claim %s" % (claims.get(ref), cid, ref))
                claims[ref] = cid


class TestYamlRoundTrip(unittest.TestCase):
    """Every workflow must survive parse -> emit -> parse unchanged, since the
    generator and the parser are two halves of the same contract."""

    def test_workflows_round_trip(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        from minyaml import parse_file, parse
        from yamlemit import dump_document
        base = os.path.join(ROOT, "sdlc", "workflows")
        for name in sorted(os.listdir(base)):
            if not name.endswith((".yaml", ".yml")):
                continue
            with self.subTest(workflow=name):
                original = parse_file(os.path.join(base, name))
                self.assertEqual(parse(dump_document(original)), original)


class TestDocumentation(unittest.TestCase):
    def test_required_docs_exist(self):
        required = ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "GOVERNANCE.md", "SECURITY.md",
                    "docs/architecture.md", "docs/organization.md", "docs/agent-model.md",
                    "docs/skills.md", "docs/hooks.md", "docs/agent-teams.md", "docs/sdlc.md",
                    "docs/governance.md", "docs/security.md", "docs/model-policy.md",
                    "docs/project-onboarding.md", "docs/evaluation.md", "docs/development.md",
                    "docs/release.md", "docs/troubleshooting.md", "docs/knowledge-structure.md",
                    "docs/mcp.md", "docs/gitlab.md", "docs/limitations.md",
                    "docs/approvals.md", "docs/execution.md", "docs/organization-freeze.md", "docs/department-cycles.md",
                    "docs/getting-started.md", "docs/communications.md", "docs/production-readiness.md",
                    "docs/enterprise-deployment.md", "docs/lsp.md", "docs/work-items.md", "docs/telemetry.md",
                    "docs/liveness-and-limits.md"]
        missing = [p for p in required if not os.path.exists(os.path.join(ROOT, p))]
        self.assertEqual(missing, [], "missing documentation: %s" % missing)

    def test_every_agent_and_skill_is_listed_in_the_catalogue(self):
        with open(os.path.join(ROOT, "docs", "organization.md"), encoding="utf-8") as fh:
            org = fh.read()
        for name in os.listdir(os.path.join(ROOT, "agents")):
            self.assertTrue(name[:-3] in org, "%s missing from docs/organization.md" % name)
        with open(os.path.join(ROOT, "docs", "skills.md"), encoding="utf-8") as fh:
            skills_doc = fh.read()
        for name in os.listdir(os.path.join(ROOT, "skills")):
            if os.path.isdir(os.path.join(ROOT, "skills", name)):
                self.assertTrue(name in skills_doc, "%s missing from docs/skills.md" % name)


if __name__ == "__main__":
    unittest.main()


class TestSessionContextHook(unittest.TestCase):
    """The SessionStart hook reconciles the project's team expectation with reality.

    It also must never fail silently: it swallows exceptions by design, so a bug
    inside it produces no context at all rather than an error. Only a test that
    asserts output catches that.
    """

    def run_hook(self, expected=None, env_enabled=False):
        import tempfile
        with tempfile.TemporaryDirectory() as proj:
            if expected is not None:
                os.makedirs(os.path.join(proj, ".ai-engineering"))
                with open(os.path.join(proj, ".ai-engineering", "project.yaml"), "w") as fh:
                    fh.write("project:\n  name: demo\nai:\n  agent_teams_available: %s\n"
                             % str(expected).lower())
            env = dict(os.environ)
            env["CLAUDE_PLUGIN_ROOT"] = ROOT
            env.pop("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", None)
            if env_enabled:
                env["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "hooks", "scripts", "session_context.py")],
                input="{}", capture_output=True, text=True, cwd=proj, env=env, timeout=60)
            self.assertTrue(proc.stdout.strip(),
                            "the hook produced no context at all: %s" % proc.stderr[-400:])
            return json.loads(proc.stdout)["additionalContext"]

    def test_it_always_produces_context(self):
        for expected in (None, True, False):
            for enabled in (True, False):
                with self.subTest(expected=expected, enabled=enabled):
                    self.assertIn("AI Engineering OS is active",
                                  self.run_hook(expected, enabled))

    def test_teams_enabled_against_a_project_that_does_not_expect_them_is_flagged(self):
        text = self.run_hook(expected=False, env_enabled=True)
        self.assertIn("ENABLED", text)
        self.assertIn("stalls", text)

    def test_a_project_expecting_teams_without_the_variable_is_told_to_degrade(self):
        text = self.run_hook(expected=True, env_enabled=False)
        self.assertIn("degraded_mode", text)

    def test_teams_off_and_not_expected_says_nothing(self):
        self.assertNotIn("Agent team", self.run_hook(expected=False, env_enabled=False))

    def test_the_project_flag_is_read_by_code_not_only_by_prose(self):
        """Regression: ai.agent_teams_available was declared in the template and
        consumed nowhere, so the fallback contract could not hold."""
        hits = subprocess.run(["grep", "-rl", "agent_teams_available",
                               os.path.join(ROOT, "hooks"), os.path.join(ROOT, "scripts")],
                              capture_output=True, text=True).stdout.split()
        self.assertTrue(hits, "no hook or script reads ai.agent_teams_available")


class TestHookPolicyDocumentation(unittest.TestCase):
    """A rule nobody documented is a rule nobody can review."""

    def setUp(self):
        self.rules = load("policies/hook-policy.json")["rules"]
        with open(os.path.join(ROOT, "docs", "hooks.md"), encoding="utf-8") as fh:
            self.doc = fh.read()

    def test_the_documented_rule_count_matches_the_policy(self):
        match = re.search(r"(\d+) rules in `policies/hook-policy\.json`", self.doc)
        self.assertIsNotNone(match, "docs/hooks.md no longer states a rule count")
        self.assertEqual(int(match.group(1)), len(self.rules))

    def test_every_rule_id_appears_in_the_category_table(self):
        # The table uses ranges (SH-01…SH-05), so expand them before comparing.
        documented = set()
        for prefix, lo, hi in re.findall(r"([A-Z]+)-(\d+)…[A-Z]*-?(\d+)", self.doc):
            documented |= {"%s-%02d" % (prefix, n) for n in range(int(lo), int(hi) + 1)}
        documented |= set(re.findall(r"\b[A-Z]{2,3}-\d{2}\b", self.doc))
        missing = sorted(r["id"] for r in self.rules if r["id"] not in documented)
        self.assertEqual(missing, [], "undocumented rules: %s" % missing)

    def test_every_rule_declares_an_action_the_semantics_define(self):
        allowed = set(load("policies/hook-policy.json")["action_semantics"])
        for rule in self.rules:
            with self.subTest(rule=rule["id"]):
                self.assertIn(rule["action"], allowed)


class TestWirePermissionDecisions(unittest.TestCase):
    """Every decision a guard emits must be one Claude Code actually accepts.

    Regression for the worst defect this repository has had. The guards emitted
    `permissionDecision: "escalate"` -- a word from the organization's vocabulary
    that is not in the platform's schema. Claude Code discards a decision it
    cannot parse and the tool call PROCEEDS, so all 25 escalate-tier rules, the
    credential and control-plane tiers of guard_write, and the guard-failure
    handler were inert. Every existing test passed, because they all asserted the
    guard's own output rather than what the platform does with it.
    """

    #  Claude Code's PreToolUse schema. Verified against the CLI's own zod enum.
    PLATFORM = ("allow", "deny", "ask", "defer")

    def test_the_translation_table_targets_only_platform_values(self):
        sys.path.insert(0, os.path.join(ROOT, "hooks", "lib"))
        import hooklib
        for org, wire in hooklib.WIRE_DECISION.items():
            with self.subTest(org=org):
                self.assertIn(wire, self.PLATFORM,
                              "%r maps to %r, which Claude Code would discard" % (org, wire))

    def test_no_guard_ever_emits_a_value_off_the_schema(self):
        """Drive every guard across both tiers and inspect the actual JSON."""
        cases = [
            ("guard_bash", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}),
            ("guard_bash", {"tool_name": "Bash", "tool_input": {"command": "terraform destroy"}}),
            ("guard_bash", {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}),
            ("guard_write", {"tool_name": "Write", "agent_type": "qa-engineer",
                             "tool_input": {"file_path": "/home/u/.ssh/id_rsa", "content": "x"}}),
            ("guard_write", {"tool_name": "Write", "agent_type": "qa-engineer",
                             "tool_input": {"file_path": "src/app.py", "content": "x"}}),
            ("guard_spawn", {"tool_name": "Agent", "agent_type": "backend-developer",
                             "tool_input": {"subagent_type": "engineering-director"}}),
        ]
        seen = set()
        for guard, payload in cases:
            proc = subprocess.run(
                [sys.executable, os.path.join(ROOT, "hooks", "scripts", guard + ".py")],
                input=json.dumps(payload), capture_output=True, text=True, timeout=30)
            out = (proc.stdout or "").strip()
            if not out:
                continue
            decision = json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision")
            if decision is None:
                continue
            seen.add(decision)
            with self.subTest(guard=guard, cmd=str(payload["tool_input"])[:60]):
                self.assertIn(decision, self.PLATFORM,
                              "%s emitted %r, which Claude Code discards -- the call proceeds"
                              % (guard, decision))
        self.assertTrue({"deny", "ask"} <= seen,
                        "the cases must exercise both tiers; saw %s" % sorted(seen))

    def test_escalate_never_reaches_the_wire(self):
        for path in ("hooks/scripts/guard_bash.py", "hooks/scripts/guard_write.py",
                     "hooks/scripts/guard_spawn.py", "hooks/lib/hooklib.py"):
            with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
                body = fh.read()
            for line in body.splitlines():
                if '"permissionDecision"' in line and "escalate" in line:
                    self.fail("%s emits escalate directly: %s" % (path, line.strip()))


class TestCycleAcceptance(unittest.TestCase):
    """Every cycle declares check_dod.py as the thing that determines acceptance.

    That was a claim about a mode the script did not have: acceptance was whatever
    the department lead wrote into the rollup, and no validator noticed because
    cycle acceptance conditions were never even grammar-checked.
    """

    def cycles(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        import check_dod
        return check_dod.cycles()

    def test_every_cycle_names_a_mechanism_that_exists(self):
        proc = script("check_dod.py", "--help")
        self.assertIn("--cycle", proc.stdout)
        for cid, cyc in self.cycles().items():
            with self.subTest(cycle=cid):
                determined = (cyc.get("acceptance") or {}).get("determined_by", "")
                self.assertIn("check_dod", determined)
                self.assertTrue((cyc.get("acceptance") or {}).get("conditions"),
                                "%s declares no acceptance conditions to determine" % cid)

    def test_every_cycle_can_actually_be_evaluated(self):
        import tempfile
        with tempfile.TemporaryDirectory() as project:
            for cid in self.cycles():
                with self.subTest(cycle=cid):
                    proc = script("check_dod.py", "--cycle", cid, "--project", project)
                    self.assertNotIn("unknown cycle", proc.stdout)
                    self.assertNotEqual(proc.returncode, 2,
                                        "%s could not be evaluated: %s" % (cid, proc.stdout))
                    # An empty project satisfies nothing, so acceptance must be refused.
                    self.assertIn("NOT ACCEPTED", proc.stdout)

    def test_unmet_evidence_is_not_reported_as_success(self):
        """Exit 0 means done. Evidence that has not been supplied is not done."""
        import tempfile
        with tempfile.TemporaryDirectory() as project:
            proc = script("check_dod.py", "--workflow", "WF-FEATURE", "--stage", "CI",
                          "--project", project)
            self.assertIn("REQUIRES-EVIDENCE", proc.stdout)
            self.assertNotEqual(proc.returncode, 0,
                                "a stage with unmet evidence exited 0, which reads as done")

    def test_cycle_acceptance_conditions_are_grammar_checked(self):
        """Regression: a typo in a cycle condition used to pass every validator."""
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "p")
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git"))
            path = os.path.join(dst, "sdlc", "cycles", "dev.yaml")
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(body.replace("agent_verdict(code-reviewer, pass)",
                                      "no_such_predicate(code-reviewer, pass)"))
            proc = subprocess.run([sys.executable, os.path.join(dst, "scripts", "check_dod.py"),
                                   "--grammar"], capture_output=True, text=True, cwd=dst, timeout=120)
            self.assertIn("unknown predicate no_such_predicate", proc.stdout)
            self.assertNotEqual(proc.returncode, 0)


class TestStopHook(unittest.TestCase):
    """The Stop hook is the one place the lifecycle is enforced rather than asked for.

    It must block on a structural fault, stay silent otherwise, and never trap a
    session: a gate that cannot be escaped is worse than no gate.
    """

    HOOK = os.path.join(ROOT, "hooks", "scripts", "check_artifacts.py")

    def run_stop(self, header, active=False):
        import tempfile, time
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as data:
            art = os.path.join(proj, "a.md")
            with open(art, "w", encoding="utf-8") as fh:
                fh.write(header)
            audit = os.path.join(data, "audit")
            os.makedirs(audit)
            with open(os.path.join(audit, time.strftime("%Y-%m") + ".jsonl"), "w") as fh:
                fh.write(json.dumps({"type": "file_change", "session": "S", "path": art}) + "\n")
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT=ROOT, CLAUDE_PLUGIN_DATA=data,
                       CLAUDE_PROJECT_DIR=proj)
            proc = subprocess.run(
                [sys.executable, self.HOOK],
                input=json.dumps({"session_id": "S", "stop_hook_active": active}),
                capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(proc.returncode, 0, "a stop hook must always exit 0")
            return json.loads(proc.stdout) if proc.stdout.strip() else None

    VALID = ("---\nid: ACME-REQ-002\ntype: requirement\ntitle: A complete header\n"
             "status: approved\n"
             "owner: requirements-analyst\nversion: 1\ncreated_at: '2026-08-20'\n"
             "updated_at: '2026-08-20'\nsource: agent\nlinks: {}\n---\n")
    INVALID = "---\nid: ACME-REQ-001\ntype: requirement\ntitle: Missing the rest\n---\n"

    def test_a_malformed_artifact_blocks_the_stop(self):
        out = self.run_stop(self.INVALID)
        self.assertIsNotNone(out, "an invalid artifact must not pass silently")
        self.assertEqual(out["decision"], "block")
        self.assertIn("a.md", out["reason"])

    def test_a_valid_artifact_says_nothing(self):
        self.assertIsNone(self.run_stop(self.VALID))

    def test_it_never_traps_a_session(self):
        """stop_hook_active means the session is already held open by a stop hook.
        Ignoring it is how a hook becomes an infinite loop."""
        self.assertIsNone(self.run_stop(self.INVALID, active=True))

    def test_it_is_registered_for_both_stop_events(self):
        cfg = load("hooks/hooks.json")["hooks"]
        for event in ("Stop", "SubagentStop"):
            with self.subTest(event=event):
                self.assertIn(event, cfg)
                cmds = [h["command"] for h in cfg[event][0]["hooks"]]
                self.assertTrue(any("check_artifacts.py" in c for c in cmds),
                                "%s no longer runs the artifact check: %s" % (event, cmds))
                for c in cmds:
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}", c)


class TestChangeScoping(unittest.TestCase):
    """Predicates must answer "this work item", not "anything done in this repo".

    Unscoped, a finished run vacuously satisfied a new one and two concurrent runs
    starved each other: one feature's IN_PROGRESS rollup failed cycle_accepted for
    every other feature in flight.
    """

    def project(self, *artifacts):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        for i, (change, status) in enumerate(artifacts):
            with open(os.path.join(d, "s%d.md" % i), "w", encoding="utf-8") as fh:
                fh.write("---\nid: ACME-STORY-%03d\ntype: story\nchange: %s\n"
                         "title: A story for scoping\nstatus: done\nowner: backend-developer\n"
                         "version: 1\ncreated_at: '2026-08-01'\nupdated_at: '2026-08-02'\n"
                         "source: agent\nlinks: {}\n"
                         # cycle_accepted now re-checks the cycle's own conditions,
                         # so an accepted CYCLE-DEV has to carry the verdict it rests on.
                         "reviewers: [{\"reviewer\": \"code-reviewer\", \"verdict\": \"pass\"}]\n"
                         "rollup:\n  cycle: CYCLE-DEV\n"
                         "  status: %s\n  produced_by: development-lead\n  at: '2026-08-02'\n"
                         "  rework_rounds: 0\n---\n" % (i + 1, change, status))
        return d

    def check(self, project, change=None):
        args = ["check_dod.py", "--workflow", "WF-FEATURE", "--stage", "DEV", "--project", project]
        if change:
            args += ["--change", change]
        return script(*args).stdout

    def test_a_concurrent_change_does_not_starve_a_finished_one(self):
        p = self.project(("ACME-EPIC-001", "ACCEPTED"), ("ACME-EPIC-002", "IN_PROGRESS"))
        out = self.check(p, "ACME-EPIC-001")
        self.assertRegex(out, r"PASS\s+cycle_accepted")

    def test_a_stale_rollup_does_not_satisfy_a_new_change(self):
        p = self.project(("ACME-EPIC-001", "ACCEPTED"))
        self.assertRegex(self.check(p, "ACME-EPIC-999"), r"FAIL\s+cycle_accepted")

    def test_an_unscoped_run_spanning_two_changes_refuses_to_answer(self):
        """Silently mixing them is what let a stale rollup satisfy a new feature."""
        p = self.project(("ACME-EPIC-001", "ACCEPTED"), ("ACME-EPIC-002", "IN_PROGRESS"))
        out = self.check(p)
        self.assertIn("Re-run with --change", out)


class TestPredicatesAreSatisfiable(unittest.TestCase):
    """A predicate its own stage cannot satisfy is a trap, not a check."""

    def artifact(self, d, name, body):
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(body)

    def evaluate(self, project, predicate):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        import check_dod
        fn, args = check_dod.parse_predicate(predicate)
        return check_dod.evaluate(fn, args, check_dod.load_artifacts(project), project)[0]

    HEAD = ("---\nid: %s\ntype: %s\nchange: ACME-INC-001\ntitle: %s\nstatus: approved\n"
            "owner: %s\nversion: 1\ncreated_at: '2026-08-01'\nupdated_at: '2026-08-02'\n"
            "source: agent\nlinks:%s\n%s---\n")

    def test_an_rca_whose_actions_are_not_defects_can_still_close(self):
        """The stage lists monitoring and process improvements as valid outcomes,
        while every_linked(RCA, DEF) demanded a defect specifically."""
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        self.artifact(d, "rca.md", self.HEAD % ("ACME-RCA-001", "rca", "Alert never fired",
                                                "rca-analyst", "\n  debt:\n    - ACME-DEBT-004", ""))
        self.artifact(d, "debt.md", self.HEAD % ("ACME-DEBT-004", "technical-debt",
                                                 "Add the missing alert", "sre", " {}", ""))
        self.assertEqual(self.evaluate(d, "every_linked(RCA, DEF)"), "FAIL")
        self.assertEqual(self.evaluate(d, "corrective_actions_tracked(RCA)"), "PASS")

    def test_a_granted_security_exception_resolves_the_finding(self):
        """CYCLE-SEC offers an exception_granted edge so a human can accept a
        standing risk. Without this the acceptance conditions could never be met,
        so the exception led nowhere."""
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        approval = ("approvals:\n  - policy_ref: AP-04\n    approver_id: gitlab:jchen\n"
                    "    approver_role: security-owner\n"
                    "    recorded_in: 'gitlab:acme/platform!482'\n    decided_at: '2026-08-02'\n")
        self.artifact(d, "sec.md", self.HEAD % ("ACME-SEC-001", "security", "Standing finding",
                                                "security-architect", " {}", approval))
        self.assertEqual(self.evaluate(d, "no_unresolved_findings(high)"), "PASS")

    def test_without_an_exception_the_finding_still_blocks(self):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        self.artifact(d, "sec.md", self.HEAD % ("ACME-SEC-002", "security", "Standing finding",
                                                "security-architect", " {}", ""))
        self.assertEqual(self.evaluate(d, "no_unresolved_findings(high)"), "REQUIRES-EVIDENCE")

    def test_a_resolved_escalation_stops_blocking_closure(self):
        """Reading the list itself as open made escalation self-punishing."""
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        base = ("---\nid: ACME-STORY-%03d\ntype: story\nchange: ACME-EPIC-0%d\ntitle: A story\n"
                "status: done\nowner: backend-developer\nversion: 1\ncreated_at: '2026-08-01'\n"
                "updated_at: '2026-08-05'\nsource: agent\nlinks: {}\nrollup:\n"
                "  cycle: CYCLE-DEV\n  status: ACCEPTED\n  produced_by: development-lead\n"
                "  at: '2026-08-05'\n  rework_rounds: 1\n  escalations:\n"
                "    - to: engineering-director\n      reason: architecture_issue\n%s---\n")
        self.artifact(d, "resolved.md", base % (1, 1, "      resolved_at: '2026-08-04'\n"))
        self.assertEqual(self.evaluate(d, "no_open_rework(CYCLE-DEV)"), "PASS")
        os.remove(os.path.join(d, "resolved.md"))
        self.artifact(d, "open.md", base % (2, 2, ""))
        self.assertEqual(self.evaluate(d, "no_open_rework(CYCLE-DEV)"), "FAIL")


class TestTheRollupStreamsAreRead(unittest.TestCase):
    """`streams` is the only field carrying per-item state, and no predicate read
    it. A rollup could declare ACCEPTED over work still in CHANGES_REQUESTED."""

    HEAD = ("---\nid: ACME-STORY-001\ntype: story\nchange: ACME-EPIC-01\ntitle: A story\n"
            "status: done\nowner: backend-developer\nversion: 1\ncreated_at: '2026-08-01'\n"
            "updated_at: '2026-08-05'\nsource: agent\nlinks: {}\n"
            "reviewers: [{\"reviewer\": \"code-reviewer\", \"verdict\": \"pass\"}]\nrollup:\n"
            "  cycle: CYCLE-DEV\n  status: ACCEPTED\n  produced_by: development-lead\n"
            "  at: '2026-08-05'\n  rework_rounds: %d\n  streams:\n%s---\n")

    def project(self, rounds, streams):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        with open(os.path.join(d, "s.md"), "w", encoding="utf-8") as fh:
            fh.write(self.HEAD % (rounds, streams))
        return d

    def evaluate(self, project, predicate):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        import check_dod
        fn, args = check_dod.parse_predicate(predicate)
        return check_dod.evaluate(fn, args, check_dod.load_artifacts(project), project)[0]

    DONE = "    - name: backend\n      state: READY_FOR_INTEGRATION\n"
    OPEN = ("    - name: backend\n      state: READY_FOR_INTEGRATION\n"
            "    - name: frontend\n      state: CHANGES_REQUESTED\n")

    def test_all_streams_done_is_accepted(self):
        d = self.project(1, self.DONE)
        self.assertEqual(self.evaluate(d, "cycle_accepted(CYCLE-DEV)"), "PASS")
        self.assertEqual(self.evaluate(d, "no_open_rework(CYCLE-DEV)"), "PASS")

    def test_a_stream_in_changes_requested_is_not_accepted(self):
        d = self.project(1, self.OPEN)
        self.assertEqual(self.evaluate(d, "cycle_accepted(CYCLE-DEV)"), "FAIL",
                         "the head declared ACCEPTED over open work and was believed")

    def test_a_stream_in_changes_requested_is_open_rework(self):
        self.assertEqual(self.evaluate(self.project(1, self.OPEN),
                                       "no_open_rework(CYCLE-DEV)"), "FAIL")

    def test_an_unrecognised_stream_state_is_not_evidence_of_completion(self):
        d = self.project(1, "    - name: backend\n      state: probably-fine\n")
        self.assertEqual(self.evaluate(d, "cycle_accepted(CYCLE-DEV)"), "FAIL")

    def test_the_round_that_triggers_escalation_does_not_pass(self):
        """The policy escalates on REACHING the limit. `>` let that round through."""
        self.assertEqual(self.evaluate(self.project(2, self.DONE),
                                       "no_open_rework(CYCLE-DEV)"), "PASS")
        self.assertEqual(self.evaluate(self.project(3, self.DONE),
                                       "no_open_rework(CYCLE-DEV)"), "FAIL")


class TestModelFloorBlocks(unittest.TestCase):
    """A risk floor that silently degrades is not a floor.

    An organization's availableModels allowlist can exclude the model a floor
    requires. Claude Code then runs on something weaker while the resolver kept
    reporting the model it wanted, so the floor read as satisfied.
    """

    def project(self, models):
        import tempfile, shutil
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, ".ai-engineering"))
        with open(os.path.join(d, ".ai-engineering", "project.yaml"), "w") as fh:
            fh.write("project:\n  name: constrained\nai:\n  available_models:\n")
            for m in models:
                fh.write("    - %s\n" % m)
        return d

    def resolve(self, role, risk, project):
        proc = script("resolve_model.py", "--role", role, "--risk", risk,
                      "--project", project, "--json")
        return json.loads(proc.stdout), proc.returncode

    def test_critical_work_blocks_when_its_model_is_unavailable(self):
        result, code = self.resolve("security-architect", "CRITICAL", self.project(["sonnet"]))
        self.assertTrue(result["blocked"])
        self.assertEqual(code, 3, "a caller reading stdout must see the block in the exit code")

    def test_high_risk_work_blocks_too(self):
        result, _ = self.resolve("solution-architect", "HIGH", self.project(["haiku"]))
        self.assertTrue(result["blocked"])

    def test_low_risk_work_proceeds_on_what_is_available(self):
        result, code = self.resolve("docs-writer", "LOW", self.project(["sonnet", "haiku"]))
        self.assertFalse(result["blocked"])
        self.assertEqual(code, 0)

    def test_an_unconstrained_organization_is_unaffected(self):
        import tempfile, shutil
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        result, code = self.resolve("security-architect", "CRITICAL", d)
        self.assertFalse(result["blocked"])
        self.assertEqual(result["model"], "opus")


class TestPluginAgentFrontmatter(unittest.TestCase):
    """Only keys Claude Code actually honours for a plugin agent may appear.

    It warns and discards permissionMode, hooks and mcpServers on plugin agents.
    Carrying one would be configuration that looks like a control and is none.
    """

    IGNORED = ("permissionMode", "hooks", "mcpServers")

    def frontmatter(self):
        out = {}
        for name in sorted(os.listdir(os.path.join(ROOT, "agents"))):
            if name.endswith(".md"):
                fm, _ = read_fm(os.path.join(ROOT, "agents", name))
                out[name] = fm
        return out

    def test_no_agent_sets_a_key_the_platform_discards(self):
        for name, fm in self.frontmatter().items():
            for key in self.IGNORED:
                with self.subTest(agent=name, key=key):
                    self.assertNotIn(key, fm)

    def test_every_agent_declares_an_effort_the_platform_accepts(self):
        allowed = {"low", "medium", "high", "xhigh", "max"}
        for name, fm in self.frontmatter().items():
            with self.subTest(agent=name):
                effort = fm.get("effort")
                self.assertIsNotNone(effort, "%s sets no effort" % name)
                if not isinstance(effort, int):
                    self.assertIn(effort, allowed)

    def test_effort_matches_the_model_policy(self):
        policy = load("policies/model-policy.json")
        registry = {a["name"]: a for a in load("policies/agent-registry.json")["agents"]}
        for name, fm in self.frontmatter().items():
            role = fm["name"]
            entry = registry.get(role)
            if not entry:
                continue
            expected = None
            for rule in policy["routing"]:
                w = rule.get("when") or {}
                if "risk" in w and entry.get("risk") not in w["risk"]:
                    continue
                if "role" in w and role not in w["role"]:
                    continue
                expected = rule.get("effort")
                break
            if expected:
                with self.subTest(agent=role):
                    self.assertEqual(fm.get("effort"), expected)


class TestChangeScopingIsLive(unittest.TestCase):
    """The scoping field must be written, not merely declared and read.

    `change` was in the header schema and read by check_dod for two releases while
    nothing wrote it. changes_present() always returned [], so the ambiguity guard
    could never fire and `--change <id>` filtered every artifact away. The engine
    reported all-green on a rule that was not running.
    """

    def project_with_two_changes(self):
        import tempfile, shutil
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        import simulate_sdlc as S
        d = tempfile.mkdtemp(prefix="aieos-scope-")
        self.addCleanup(shutil.rmtree, d, True)
        S.make_project(d)
        S.set_change("ACME-FEAT-001")
        S.write_artifact(d, "REQ", status="approved", reviewers=[S.verdict("qa-lead")])
        S.set_change("ACME-FEAT-002")
        S.write_artifact(d, "REQ", status="draft")
        return d

    def evaluate(self, project, predicate, change=None):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import check_dod
        arts = check_dod.scope_to_change(check_dod.load_artifacts(project), change)
        fn, args = check_dod.parse_predicate(predicate)
        return check_dod.evaluate(fn, args, arts, project)[0]

    def test_every_workflow_artifact_carries_its_change(self):
        d = self.project_with_two_changes()
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import check_dod
        arts = check_dod.load_artifacts(d)
        self.assertTrue(arts)
        for a in arts:
            with self.subTest(artifact=a["id"]):
                self.assertTrue(a.get("change"),
                                "%s carries no change, so it scopes to nothing" % a["id"])

    def test_a_finished_change_is_not_dragged_down_by_an_unrelated_one(self):
        d = self.project_with_two_changes()
        self.assertEqual(self.evaluate(d, "artifact_status(REQ, approved)", "ACME-FEAT-001"),
                         "PASS")
        self.assertEqual(self.evaluate(d, "artifact_status(REQ, approved)", "ACME-FEAT-002"),
                         "FAIL")

    def test_the_change_id_is_never_invented(self):
        """A made-up change id is worse than a missing one: it looks scoped and
        groups nothing."""
        import tempfile, shutil
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import simulate_sdlc as S
        d = tempfile.mkdtemp(prefix="aieos-scope-")
        self.addCleanup(shutil.rmtree, d, True)
        S.make_project(d)
        S.set_change(None)
        aid = S.write_artifact(d, "REQ", status="draft")
        import check_dod
        art = [a for a in check_dod.load_artifacts(d) if a["id"] == aid][0]
        self.assertNotIn("simulated", str(art.get("change", "")))


class TestUnusedPredicatesStillWork(unittest.TestCase):
    """Vocabulary the grammar declares but no workflow currently uses.

    Not every word has to appear in every text, but a word nothing uses and
    nothing tests is one whose implementation rots quietly and is reached for
    years later, by which time it is wrong.
    """

    def project_with_decision(self, status):
        import tempfile, shutil
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
        import simulate_sdlc as S
        d = tempfile.mkdtemp(prefix="aieos-pred-")
        self.addCleanup(shutil.rmtree, d, True)
        S.make_project(d)
        S.set_change("ACME-FEAT-001")
        aid = S.write_artifact(d, "DEC", status=status,
                               question="Which retention window applies to the audit log")
        return d, aid

    def evaluate(self, project, predicate):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import check_dod
        fn, args = check_dod.parse_predicate(predicate)
        return check_dod.evaluate(fn, args, check_dod.load_artifacts(project), project)

    def test_decision_resolved_passes_on_an_answered_decision(self):
        # "answered", not "resolved": DEC's statuses are open, answered, withdrawn,
        # superseded. Inventing one is the mistake the simulator's own validation
        # now catches, and it caught this test too.
        project, aid = self.project_with_decision("answered")
        self.assertEqual(self.evaluate(project, "decision_resolved(%s)" % aid)[0], "PASS")

    def test_decision_resolved_fails_while_it_is_open(self):
        project, aid = self.project_with_decision("open")
        status, detail = self.evaluate(project, "decision_resolved(%s)" % aid)
        self.assertEqual(status, "FAIL")
        self.assertIn(aid, detail)

    def test_decision_resolved_fails_when_the_decision_does_not_exist(self):
        """Naming a decision that is not there is a mistake, not a pass."""
        project, _ = self.project_with_decision("answered")
        self.assertEqual(self.evaluate(project, "decision_resolved(ACME-DEC-999)")[0], "FAIL")

