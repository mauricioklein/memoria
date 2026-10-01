import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin" / "memoria"
PROJECTS = REPO_ROOT / "projects"


class RagCliTest(unittest.TestCase):
    def setUp(self):
        self.slug = "testrag-" + uuid.uuid4().hex[:8]
        self.project_dir = PROJECTS / self.slug
        self.cli("init", "--project", self.slug, "--title", "Test RAG", "--owner", "Tester")

        self.cli(
            "new-resource", "--project", self.slug, "--category", "decisions", "--title", "Sync source strategy",
            "--type", "decision", "--source", "manual", "--source-ref", "manual", "--summary", "Use sqlite-backed local RAG",
            "--tags", "sync,rag,sqlite", "--created", "2026-06-14",
            input_text="We decided to use a local sqlite index for sync source questions.\n",
        )
        self.cli(
            "new-resource", "--project", self.slug, "--category", "notes", "--title", "Weekly review",
            "--type", "note", "--source", "manual", "--source-ref", "manual", "--summary", "Linked follow-up note",
            "--tags", "review,rag", "--created", "2026-06-14",
            input_text="See [the decision](../decisions/2026-06-14-sync-source-strategy.md).\n",
        )
        self.cli(
            "new-resource", "--project", self.slug, "--category", "decisions", "--title", "Conference venue",
            "--type", "decision", "--source", "manual", "--source-ref", "manual", "--summary", "Pick the conference venue",
            "--tags", "conference,venue,events", "--created", "2026-06-14",
            input_text="We decided to host the conference at Riverside Hall because the room fits the workshop format.\n",
        )
        readme = "# Test RAG\n\nProject goal is local retrieval.\n\nSee resources/decisions/2026-06-14-sync-source-strategy.md.\n"
        self.cli("update-resource", "--project", self.slug, "--path", "README.md", "--change", "seed readme", input_text=readme)
        self.cli("rag", "rebuild", "--project", self.slug)

    def tearDown(self):
        if self.project_dir.exists():
            shutil.rmtree(self.project_dir)

    def cli(self, *args, input_text=None):
        return subprocess.check_output([str(BIN), *args], cwd=REPO_ROOT, text=True, input=input_text)

    def cli_error(self, *args):
        result = subprocess.run([str(BIN), *args], cwd=REPO_ROOT, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        return result

    def test_contributions_default_to_project_owner(self):
        note = self.project_dir / "resources" / "contributions" / "tester.md"
        content = note.read_text()
        self.assertIn("Participation — Tester (Test RAG)", content)
        self.assertIn("**Role on the project:** <role>", content)
        self.assertEqual(list(note.parent.glob("*.md")), [note])

    def test_rag_search_finds_expected_file(self):
        output = self.cli("rag", "search", "--project", self.slug, "--query", "sync source sqlite")
        self.assertIn("resources/decisions/2026-06-14-sync-source-strategy.md", output)

    def test_rag_search_json_and_paths_only(self):
        output = self.cli("rag", "search", "--project", self.slug, "--query", "local rag", "--json")
        payload = json.loads(output)
        self.assertTrue(payload)
        self.assertIn("path", payload[0])
        paths = self.cli("rag", "search", "--project", self.slug, "--query", "local rag", "--paths-only")
        self.assertIn("README.md", paths)
        self.assertIn("resources/decisions/2026-06-14-sync-source-strategy.md", paths)

    def test_rag_search_context_and_punctuation_query(self):
        output = self.cli(
            "rag", "search", "--project", self.slug,
            "--query", "what did we decide about sync-source strategy?",
            "--format", "context",
        )
        self.assertIn("# Memoria RAG context for project", output)
        self.assertIn("resources/decisions/2026-06-14-sync-source-strategy.md", output)

    def test_rag_search_dedupes_to_one_hit_per_file(self):
        payload = json.loads(self.cli("rag", "search", "--project", self.slug, "--query", "local sync rag", "--json"))
        paths = [item["path"] for item in payload]
        self.assertEqual(len(paths), len(set(paths)))

    def test_rag_related_aggregates_by_path(self):
        output = self.cli(
            "rag", "related", "--project", self.slug,
            "--path", "resources/decisions/2026-06-14-sync-source-strategy.md",
        )
        self.assertIn("kinds: markdown-link", output)
        self.assertIn("README.md", output)
        paths = [line[2:] for line in output.splitlines() if line.startswith("- ")]
        self.assertEqual(len(paths), len(set(paths)))

    def test_rag_update_removes_deleted_file(self):
        os.remove(self.project_dir / "resources" / "notes" / "2026-06-14-weekly-review.md")
        self.cli("rag", "update", "--project", self.slug)
        output = self.cli("rag", "search", "--project", self.slug, "--query", "linked follow-up")
        self.assertNotIn("resources/notes/2026-06-14-weekly-review.md", output)

    def test_rag_stats_and_doctor_json(self):
        stats = json.loads(self.cli("rag", "stats", "--project", self.slug, "--json"))
        self.assertGreaterEqual(stats["files"], 3)
        self.assertIn("db_path", stats)
        doctor = json.loads(self.cli("rag", "doctor", "--project", self.slug, "--json"))
        self.assertTrue(doctor["ok"])

    def test_rag_search_returns_file_line_numbers(self):
        payload = json.loads(self.cli("rag", "search", "--project", self.slug, "--query", "local sqlite index", "--json"))
        decision = next(item for item in payload if item["path"] == "resources/decisions/2026-06-14-sync-source-strategy.md")
        self.assertGreater(decision["line_start"], 1)

    def test_rag_search_handles_natural_language_query(self):
        payload = json.loads(self.cli("rag", "search", "--project", self.slug, "--query", "what did we decide about the conference venue?", "--json"))
        self.assertEqual(payload[0]["path"], "resources/decisions/2026-06-14-conference-venue.md")

    def test_rag_search_is_deterministic_on_repeated_runs(self):
        first = json.loads(self.cli("rag", "search", "--project", self.slug, "--query", "rag", "--json"))
        second = json.loads(self.cli("rag", "search", "--project", self.slug, "--query", "rag", "--json"))
        self.assertEqual([item["path"] for item in first], [item["path"] for item in second])

    def test_setup_agent_dry_run_succeeds_for_pi(self):
        output = self.cli("setup", "agent", "--harness", "pi", "--dry-run")
        self.assertIn("Harness: pi", output)

    def test_every_supported_harness_has_a_template(self):
        harnesses = ["claude", "pi", "codex", "opencode", "generic"]
        for harness in harnesses:
            template_root = REPO_ROOT / "adapters" / harness / "files"
            self.assertTrue(template_root.is_dir(), str(template_root))
            self.assertTrue(any(template_root.iterdir()), str(template_root))

    def test_generated_adapter_includes_retrieval_first_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.cli("setup", "agent", "--harness", "claude", "--dest", tmpdir)
            content = (Path(tmpdir) / "CLAUDE.md").read_text()
        self.assertIn("rag search --project <slug>", content)
        self.assertIn("rag related --project <slug>", content)
        self.assertIn("Start with retrieval before broad scanning", content)
        self.assertIn("relative to the Memoria repo root", content)
        self.assertIn("cd` to the repo root", content)

    def test_rag_missing_project_errors_cleanly(self):
        error = self.cli_error("rag", "search", "--project", "missing-project", "--query", "anything")
        self.assertIn("project not found", error.stderr)


if __name__ == "__main__":
    unittest.main()
