"""Asking the repository what order its work has to happen in.

policies/coupling-policy.json says file disjointness is necessary and not
sufficient, and implemented only the sufficient half. These tests are about the
necessary half, and mostly about the cases where inferring something would be
wrong: a bare import that names nothing owned, a mutual import with no order in
it, a history correlation that says which files move together and not which one
moves first.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import workitem as W  # noqa: E402


def git(project, *args):
    return subprocess.run(["git", "-C", project] + list(args),
                          capture_output=True, text=True, timeout=60)


class Repo(unittest.TestCase):
    ITEM = "SFTP-FEAT-001"

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix="aieos-dep-")
        self.addCleanup(shutil.rmtree, self.project, True)
        os.makedirs(os.path.join(self.project, ".ai-engineering"))
        src = os.path.join(ROOT, "templates", "project", "project.yaml")
        with open(src, encoding="utf-8") as fh:
            cfg = fh.read().replace("    blocking: true", "    blocking: false")
        with open(os.path.join(self.project, ".ai-engineering", "project.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(cfg)

    def write(self, rel, text):
        path = os.path.join(self.project, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, message="change"):
        if not os.path.exists(os.path.join(self.project, ".git")):
            git(self.project, "init", "-q")
        git(self.project, "add", "-A")
        git(self.project, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", message)

    def plan(self):
        for argv in (["open", "--type", "feature", "--risk", "HIGH",
                      "--intent", "Inferring order from the code being changed"],
                     ["plan", "--item", self.ITEM]):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "control_loop.py")]
                           + argv + ["--project", self.project], capture_output=True, timeout=120)

    def decompose(self, children):
        graph = W.load_graph(self.project, self.ITEM)
        dev = next(t for t in graph["tasks"] if t.get("stage") == "DEV")
        made = W.graft(graph, dev["id"], children, mode="proposed")
        W.save_graph(self.project, graph)
        return {c["key"]: t["id"] for c, t in zip(children, made)}

    def infer(self, *extra):
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "infer_dependencies.py"),
             "--project", self.project, "--item", self.ITEM] + list(extra),
            capture_output=True, text=True, timeout=180)

    def as_json(self):
        return json.loads(self.infer("--json").stdout)

    def deps(self, tid):
        return W.task(W.load_graph(self.project, self.ITEM), tid).get("depends_on") or []


class TestImportEdges(Repo):
    def setUp(self):
        Repo.setUp(self)
        self.write("src/payments/model.py", "class Payment:\n    pass\n")
        self.write("src/payments/service.py",
                   "from src.payments.model import Payment\nimport json\n")
        self.write("src/api/handler.py", "from src.payments.service import charge\n")
        self.commit("initial")
        self.plan()
        self.ids = self.decompose([
            {"key": "model", "title": "Define the payment model", "role": "backend-developer",
             "owns_paths": ["src/payments/model.py"]},
            {"key": "service", "title": "Implement the charge service", "role": "backend-developer",
             "owns_paths": ["src/payments/service.py"]},
            {"key": "handler", "title": "Expose the charge endpoint", "role": "backend-developer",
             "owns_paths": ["src/api/handler.py"]},
        ])

    def test_the_importer_waits_for_what_it_imports(self):
        edges = {(e["dependent"], e["dependency"]) for e in self.as_json()["edges"]}
        self.assertIn((self.ids["service"], self.ids["model"]), edges)
        self.assertIn((self.ids["handler"], self.ids["service"]), edges)

    def test_the_edge_carries_the_line_that_produced_it(self):
        edge = next(e for e in self.as_json()["edges"]
                    if e["dependent"] == self.ids["service"])
        self.assertIn("src/payments/service.py", edge["evidence"])
        self.assertIn("model", edge["evidence"])

    def test_a_standard_library_import_infers_nothing(self):
        """`import json` must not claim a task because some file is named json."""
        for e in self.as_json()["edges"]:
            self.assertNotIn("'json'", e["evidence"])

    def test_recording_produces_a_working_order(self):
        self.infer("--record")
        self.assertIn(self.ids["model"], self.deps(self.ids["service"]))
        self.assertIn(self.ids["service"], self.deps(self.ids["handler"]))

    def test_the_recorded_edge_keeps_its_evidence(self):
        self.infer("--record")
        t = W.task(W.load_graph(self.project, self.ITEM), self.ids["service"])
        derived = t["derived_depends_on"]
        self.assertEqual(derived[0]["task"], self.ids["model"])
        self.assertEqual(derived[0]["signal"], "import_edge")
        self.assertTrue(derived[0]["evidence"])

    def test_it_is_idempotent(self):
        self.infer("--record")
        before = self.deps(self.ids["service"])
        self.infer("--record")
        self.assertEqual(before, self.deps(self.ids["service"]))

    def test_the_chain_still_parallelises_where_the_code_allows(self):
        self.write("tests/test_service.py", "from src.payments.service import charge\n")
        self.commit("tests")
        graph = W.load_graph(self.project, self.ITEM)
        dev = next(t for t in graph["tasks"] if t.get("stage") == "DEV")
        W.graft(graph, dev["id"], [
            {"key": "t", "title": "Cover the charge path", "role": "qa-engineer",
             "owns_paths": ["tests/test_service.py"]},
            {"key": "t2", "title": "Cover the model", "role": "qa-engineer",
             "owns_paths": ["tests/test_model.py"]}], mode="proposed") \
            if not dev.get("synthesis") else None
        self.infer("--record")
        graph = W.load_graph(self.project, self.ITEM)
        decomposed = {t["parent"] for t in graph["tasks"] if t.get("parent")}
        for t in graph["tasks"]:
            # Not the decomposed stages: a parent stands for its pieces, and
            # accepting one over an open child is refused on the write.
            if not t.get("parent") and t["id"] not in decomposed:
                t["state"] = "accepted"
        for key in ("model", "service"):
            W.task(graph, self.ids[key])["state"] = "accepted"
        W.save_graph(self.project, graph)
        offered = [t["id"] for t in W.runnable(W.load_graph(self.project, self.ITEM))]
        self.assertIn(self.ids["handler"], offered)


class TestPathOverlap(Repo):
    def test_two_tasks_editing_one_file_are_ordered(self):
        self.write("src/shared.py", "x = 1\n")
        self.commit("initial")
        self.plan()
        ids = self.decompose([
            {"key": "a", "title": "Change the shared module", "role": "backend-developer",
             "owns_paths": ["src/shared.py"]},
            {"key": "b", "title": "Also change the shared module", "role": "backend-developer",
             "owns_paths": ["src/shared.py"]},
        ])
        edges = self.as_json()["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["signal"], "path_overlap")
        self.assertEqual((edges[0]["dependent"], edges[0]["dependency"]),
                         (ids["b"], ids["a"]))

    def test_a_glob_matching_nothing_is_reported(self):
        self.write("src/real.py", "x = 1\n")
        self.commit("initial")
        self.plan()
        self.decompose([
            {"key": "a", "title": "Change the real module", "role": "backend-developer",
             "owns_paths": ["src/real.py"]},
            {"key": "b", "title": "Change an imagined module", "role": "backend-developer",
             "owns_paths": ["src/imagined/**"]},
        ])
        notes = " ".join(self.as_json()["notes"])
        self.assertIn("matches no file", notes)


class TestMutualImports(Repo):
    """Two modules that import each other have no order between them, and
    picking one on iteration order is a decision made by nobody."""

    def setUp(self):
        Repo.setUp(self)
        self.write("src/a.py", "from src.b import y\n")
        self.write("src/b.py", "from src.a import x\n")
        self.commit("initial")
        self.plan()
        self.ids = self.decompose([
            {"key": "a", "title": "Work on module a", "role": "backend-developer",
             "owns_paths": ["src/a.py"]},
            {"key": "b", "title": "Work on module b", "role": "backend-developer",
             "owns_paths": ["src/b.py"]},
        ])

    def test_neither_direction_is_inferred(self):
        self.assertEqual(self.as_json()["edges"], [])

    def test_it_says_why(self):
        notes = " ".join(self.as_json()["notes"])
        self.assertIn("each import the other", notes)

    def test_recording_adds_nothing(self):
        self.infer("--record")
        for key in ("a", "b"):
            self.assertNotIn(self.ids["b" if key == "a" else "a"], self.deps(self.ids[key]))


class TestHistoryIsEvidenceNotAnOrder(Repo):
    """A coupling through a queue name or a column appears in no import. The
    history sees it, and says nothing about which side moves first."""

    def setUp(self):
        Repo.setUp(self)
        self.write("src/worker.py", "handler\n")
        self.write("config/queues.yaml", "queue: payments\n")
        self.write("src/unrelated.py", "other\n")
        self.commit("initial")
        for i in range(4):
            with open(os.path.join(self.project, "src/worker.py"), "a") as fh:
                fh.write("step%d\n" % i)
            with open(os.path.join(self.project, "config/queues.yaml"), "a") as fh:
                fh.write("  retries: %d\n" % i)
            self.commit("queue change %d" % i)
        self.plan()
        self.ids = self.decompose([
            {"key": "w", "title": "Change the worker behaviour", "role": "backend-developer",
             "owns_paths": ["src/worker.py"]},
            {"key": "q", "title": "Retune the queue configuration", "role": "devops-engineer",
             "owns_paths": ["config/queues.yaml"]},
            {"key": "u", "title": "An unrelated tidy-up", "role": "backend-developer",
             "owns_paths": ["src/unrelated.py"]},
        ])

    def test_the_pair_is_reported(self):
        pairs = [set(h["tasks"]) for h in self.as_json()["co_change"]]
        self.assertIn({self.ids["w"], self.ids["q"]}, pairs)

    def test_an_unrelated_file_is_not_reported(self):
        for h in self.as_json()["co_change"]:
            self.assertNotIn(self.ids["u"], h["tasks"])

    def test_it_is_never_recorded_as_an_edge(self):
        self.infer("--record")
        graph = W.load_graph(self.project, self.ITEM)
        for key in ("w", "q"):
            t = W.task(graph, self.ids[key])
            for d in t.get("derived_depends_on") or []:
                self.assertNotEqual(d["signal"], "co_change")
            self.assertNotIn(self.ids["q" if key == "w" else "w"], t["depends_on"])


class TestItSaysWhatItCannotSee(Repo):
    def test_an_unscanned_extension_is_named(self):
        self.write("src/api/schema.graphql", "type Payment { id: ID! }\n")
        self.write("src/api/handler.py", "x = 1\n")
        self.commit("initial")
        self.plan()
        self.decompose([
            {"key": "a", "title": "Define the graph schema", "role": "backend-developer",
             "owns_paths": ["src/api/schema.graphql"]},
            {"key": "b", "title": "Wire the handler", "role": "backend-developer",
             "owns_paths": ["src/api/handler.py"]},
        ])
        notes = " ".join(self.as_json()["notes"])
        self.assertIn(".graphql", notes)

    def test_the_blind_spots_are_reported_with_the_result(self):
        self.write("src/a.py", "x = 1\n")
        self.commit("initial")
        self.plan()
        out = self.as_json()
        self.assertTrue(out["cannot_see"])
        self.assertTrue(any("injection" in c or "Dynamic" in c for c in out["cannot_see"]))

    def test_no_declared_paths_means_nothing_to_infer(self):
        self.write("src/a.py", "x = 1\n")
        self.commit("initial")
        self.plan()
        out = self.as_json()
        self.assertEqual(out["edges"], [])
        self.assertIn("owns_paths", " ".join(out["notes"]))

    def test_it_works_without_git(self):
        """A project that is not a repository still has files."""
        self.write("src/a.py", "x = 1\n")
        self.write("src/b.py", "from src.a import x\n")
        self.plan()
        ids = self.decompose([
            {"key": "a", "title": "Write module a", "role": "backend-developer",
             "owns_paths": ["src/a.py"]},
            {"key": "b", "title": "Write module b", "role": "backend-developer",
             "owns_paths": ["src/b.py"]},
        ])
        out = self.as_json()
        self.assertEqual([(e["dependent"], e["dependency"]) for e in out["edges"]],
                         [(ids["b"], ids["a"])])
        self.assertIn("git", (out["history"] or "").lower())


class TestAProjectCanExtendIt(Repo):
    def test_a_project_supplied_pattern_is_used(self):
        self.write("src/a.thing", "LINK src/b.thing\n")
        self.write("src/b.thing", "base\n")
        self.commit("initial")
        with open(os.path.join(self.project, ".ai-engineering", "code-signals.json"),
                  "w", encoding="utf-8") as fh:
            json.dump({"import_patterns": {".thing": [r"LINK\s+(\S+)"]}}, fh)
        self.plan()
        ids = self.decompose([
            {"key": "b", "title": "Write the base thing", "role": "backend-developer",
             "owns_paths": ["src/b.thing"]},
            {"key": "a", "title": "Write the linking thing", "role": "backend-developer",
             "owns_paths": ["src/a.thing"]},
        ])
        edges = [(e["dependent"], e["dependency"]) for e in self.as_json()["edges"]]
        self.assertEqual(edges, [(ids["a"], ids["b"])])


if __name__ == "__main__":
    unittest.main()


class TestABareNameDoesNotClaimADirectory(Repo):
    """`import json` must not order a task because some directory is called
    json. A resolver loose enough to match any path segment invents edges that
    nothing in the code supports."""

    def test_a_standard_library_name_does_not_match_a_directory(self):
        self.write("src/json/encoder.py", "x = 1\n")
        self.write("src/app.py", "import json\nfrom src.json.encoder import x\n")
        self.commit("initial")
        self.plan()
        ids = self.decompose([
            {"key": "enc", "title": "Write the encoder module", "role": "backend-developer",
             "owns_paths": ["src/json/encoder.py"]},
            {"key": "app", "title": "Write the app module", "role": "backend-developer",
             "owns_paths": ["src/app.py"]},
        ])
        edges = self.as_json()["edges"]
        # The real import resolves; the bare stdlib name must not add a second,
        # differently-evidenced edge for the same pair, nor claim the directory.
        self.assertEqual(len(edges), 1, edges)
        self.assertEqual((edges[0]["dependent"], edges[0]["dependency"]),
                         (ids["app"], ids["enc"]))
        self.assertIn("encoder", edges[0]["evidence"])

    def test_a_bare_name_alone_infers_nothing(self):
        self.write("src/json/encoder.py", "x = 1\n")
        self.write("src/app.py", "import json\n")
        self.commit("initial")
        self.plan()
        self.decompose([
            {"key": "enc", "title": "Write the encoder module", "role": "backend-developer",
             "owns_paths": ["src/json/encoder.py"]},
            {"key": "app", "title": "Write the app module", "role": "backend-developer",
             "owns_paths": ["src/app.py"]},
        ])
        self.assertEqual(self.as_json()["edges"], [],
                         "a bare stdlib import claimed a task by directory name")


class TestALongerCycleIsRefused(Repo):
    """Three modules importing in a ring. The mutual-import guard only sees pairs,
    so the graph-level check is the one that has to catch this."""

    def setUp(self):
        Repo.setUp(self)
        self.write("src/a.py", "from src.c import z\n")
        self.write("src/b.py", "from src.a import x\n")
        self.write("src/c.py", "from src.b import y\n")
        self.commit("initial")
        self.plan()
        self.ids = self.decompose([
            {"key": "a", "title": "Work on module a", "role": "backend-developer",
             "owns_paths": ["src/a.py"]},
            {"key": "b", "title": "Work on module b", "role": "backend-developer",
             "owns_paths": ["src/b.py"]},
            {"key": "c", "title": "Work on module c", "role": "backend-developer",
             "owns_paths": ["src/c.py"]},
        ])

    def test_all_three_edges_are_seen(self):
        self.assertEqual(len(self.as_json()["edges"]), 3)

    def test_the_graph_does_not_become_cyclic(self):
        proc = self.infer("--record")
        self.assertIn("cyclic", proc.stdout)
        graph = W.load_graph(self.project, self.ITEM)
        edges = {t["id"]: set(t.get("depends_on") or []) for t in graph["tasks"]}

        def reaches(start, goal, seen=None):
            seen = seen or set()
            for nxt in edges.get(start, ()):
                if nxt == goal:
                    return True
                if nxt not in seen and reaches(nxt, goal, seen | {nxt}):
                    return True
            return False

        for tid in edges:
            self.assertFalse(reaches(tid, tid), "%s depends on itself" % tid)

    def test_it_exits_non_zero_when_it_refused_something(self):
        self.assertEqual(self.infer("--record").returncode, 1)
