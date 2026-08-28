"""The retention decision, at its boundaries.

The expensive mistake in this service is reporting a record deletable that is
not, so every test that matters is about the day the window closes and about the
hold that outranks it.
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from retention import Record, RetentionPolicy, decide, decide_all  # noqa: E402

POLICY = RetentionPolicy(30)
CREATED = datetime.date(2026, 1, 1)


class TestTheWindowBoundary(unittest.TestCase):
    def test_a_record_is_not_deletable_the_day_before_the_window_closes(self):
        d = decide(Record("r1", CREATED), POLICY, CREATED + datetime.timedelta(days=29))
        self.assertFalse(d.deletable)
        self.assertEqual(d.rule, "within-retention-window")

    def test_a_record_is_deletable_on_the_day_the_window_closes(self):
        """Inclusive of the boundary: day 30 of a 30-day window is elapsed."""
        d = decide(Record("r1", CREATED), POLICY, CREATED + datetime.timedelta(days=30))
        self.assertTrue(d.deletable)
        self.assertEqual(d.rule, "retention-window-elapsed")

    def test_a_record_created_today_is_never_deletable(self):
        self.assertFalse(decide(Record("r1", CREATED), POLICY, CREATED).deletable)

    def test_a_zero_day_policy_is_deletable_immediately(self):
        d = decide(Record("r1", CREATED), RetentionPolicy(0), CREATED)
        self.assertTrue(d.deletable)


class TestLegalHoldOutranksAge(unittest.TestCase):
    def test_an_expired_record_under_hold_is_not_deletable(self):
        d = decide(Record("r1", CREATED, on_legal_hold=True), POLICY,
                   CREATED + datetime.timedelta(days=3650))
        self.assertFalse(d.deletable)
        self.assertEqual(d.rule, "legal-hold")

    def test_the_eligible_date_is_still_reported_under_hold(self):
        """The hold is the reason it is kept, not a reason to stop computing when
        it would otherwise have been due."""
        d = decide(Record("r1", CREATED, on_legal_hold=True), POLICY, CREATED)
        self.assertEqual(d.eligible_on, CREATED + datetime.timedelta(days=30))


class TestMalformedInputRaises(unittest.TestCase):
    """No permissive fallback. A record the service cannot understand must never
    reach a deletable answer."""

    def test_a_record_with_no_id_is_refused(self):
        self.assertRaises(ValueError, Record, "", CREATED)

    def test_a_record_with_a_non_date_is_refused(self):
        self.assertRaises(ValueError, Record, "r1", "2026-01-01")

    def test_a_missing_field_is_refused(self):
        self.assertRaises(ValueError, Record.from_dict, {"id": "r1"})

    def test_an_unparseable_date_is_refused(self):
        self.assertRaises(ValueError, Record.from_dict,
                          {"id": "r1", "created_on": "the first of January"})

    def test_a_negative_retention_window_is_refused(self):
        self.assertRaises(ValueError, RetentionPolicy, -1)

    def test_a_boolean_is_not_a_number_of_days(self):
        self.assertRaises(ValueError, RetentionPolicy, True)


class TestDecisionsAreExplainable(unittest.TestCase):
    def test_every_decision_names_the_rule_that_produced_it(self):
        records = [Record("a", CREATED), Record("b", CREATED, on_legal_hold=True),
                   Record("c", datetime.date(2020, 1, 1))]
        for d in decide_all(records, POLICY, datetime.date(2026, 6, 1)):
            self.assertIn(d.rule, ("legal-hold", "within-retention-window",
                                   "retention-window-elapsed"))
            self.assertTrue(d.as_dict()["eligible_on"])


if __name__ == "__main__":
    unittest.main()
