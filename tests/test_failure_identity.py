"""What makes two failures the same failure.

The loop escalates on a repeat, so this comparison decides between escalating
work that was still making progress and spinning on one that was not. Comparing
the observed wording was wrong in both directions, and both directions are tested
here.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
import failure as F  # noqa: E402


class TestTheSameFailureIsRecognised(unittest.TestCase):
    def ident(self, message, cls="test_failure", sig=None):
        return F.identity(cls, sig, message)

    def test_one_failure_described_two_ways(self):
        self.assertTrue(F.same(self.ident("API returns 401 on the token endpoint"),
                               self.ident("Endpoint continues returning 401")))

    def test_the_same_facts_in_a_different_order(self):
        """A reworded report is not a new failure."""
        self.assertTrue(F.same(self.ident("AssertionError in tests/auth/test_login.py"),
                               self.ident("tests/auth/test_login.py raised AssertionError")))

    def test_an_explicit_signature_beats_any_wording(self):
        a = self.ident("first wording entirely", sig="AUTH-401-MISSING-TOKEN")
        b = self.ident("completely different prose", sig="AUTH-401-MISSING-TOKEN")
        self.assertTrue(F.same(a, b))


class TestDifferentFailuresStayDifferent(unittest.TestCase):
    def test_two_uninformative_reports_are_not_a_repeat(self):
        """The asymmetry that matters: a wrong "same" escalates work that was
        making progress, while a wrong "different" costs one attempt inside a
        bound that already exists."""
        a = F.identity("test_failure", None, "failed")
        b = F.identity("test_failure", None, "failed")
        self.assertEqual(a[1], F.NO_SIGNATURE)
        self.assertFalse(F.same(a, b))

    def test_different_exceptions_are_different(self):
        self.assertFalse(F.same(F.identity("test_failure", None, "TimeoutError after 30s"),
                                F.identity("test_failure", None, "ConnectionError after 30s")))

    def test_the_same_signature_in_a_different_class_is_different(self):
        """Signature alone would collide across kinds."""
        self.assertFalse(F.same(F.identity("test_failure", "X-1", None),
                                F.identity("review_rejected", "X-1", None)))

    def test_noise_words_do_not_make_a_signature(self):
        for text in ("error", "the test failed", "exception occurred", "failure"):
            with self.subTest(text=text):
                self.assertEqual(F.identity("unknown", None, text)[1], F.NO_SIGNATURE)


class TestDerivation(unittest.TestCase):
    def test_it_keeps_identifying_tokens(self):
        for text, token in (("raised ValueError in the parser", "ValueError"),
                            ("HTTP 503 from the registry", "503"),
                            ("tests/api/test_upload.py failed", "tests/api/test_upload.py"),
                            ("AUTH-401-MISSING-TOKEN", "AUTH-401-MISSING-TOKEN")):
            with self.subTest(text=text):
                self.assertNotEqual(F.derive(text), F.NO_SIGNATURE,
                                    "nothing identifying found in %r" % text)

    def test_an_unknown_class_falls_back_rather_than_erroring(self):
        self.assertEqual(F.identity("not-a-class", "X-1", None)[0], "unknown")
