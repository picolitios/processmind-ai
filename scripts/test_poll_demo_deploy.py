"""Verify the public CI gate rejects stale and untrusted workflow runs."""

import unittest

from poll_demo_deploy import approved_commit

SHA = "a" * 40
VALID_RUN = {
    "head_sha": SHA,
    "head_repository": {"full_name": "picolitios/processmind-ai"},
    "head_branch": "main",
    "event": "push",
    "status": "completed",
    "conclusion": "success",
}


class PollDemoDeployTest(unittest.TestCase):
    def test_only_current_main_push_is_approved(self) -> None:
        self.assertEqual(approved_commit(VALID_RUN, SHA), SHA)
        self.assertIsNone(approved_commit(VALID_RUN, "b" * 40))

    def test_untrusted_or_incomplete_runs_are_rejected(self) -> None:
        for field, value in (
            ("head_repository", {"full_name": "other/fork"}),
            ("head_branch", "feature"),
            ("event", "pull_request"),
            ("status", "in_progress"),
            ("conclusion", "failure"),
            ("head_sha", "not-a-sha"),
        ):
            with self.subTest(field=field):
                self.assertIsNone(approved_commit({**VALID_RUN, field: value}, SHA))


if __name__ == "__main__":
    unittest.main()
