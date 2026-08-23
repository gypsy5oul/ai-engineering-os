"""What makes two failures the same failure.

The loop escalates when the same thing fails twice, so the comparison decides
whether work escalates prematurely or spins. Comparing the observed text was
wrong in both directions:

    "API returns 401"                 }  one failure,
    "endpoint still returns 401"      }  read as two

    "failed"                          }  two unrelated causes,
    "failed"                          }  read as one

So a failure has an identity separate from its description: a `class` and a
`signature`. The signature is supplied by whoever saw the failure where possible,
and derived where not.

Derivation is deliberately conservative. It keeps only tokens that identify a
failure -- exception names, status codes, test paths, error identifiers -- and
throws prose away. When nothing identifying survives, it returns a signature that
matches nothing, **including another copy of itself**. That asymmetry is on
purpose: a wrong "these are the same" escalates work that was still making
progress, while a wrong "these differ" costs one more attempt inside a bound that
already exists.
"""
import hashlib
import re

CLASSES = ("test_failure", "review_rejected", "contract_conflict", "missing_information",
           "dependency_unavailable", "timeout", "permission_denied", "environment", "unknown")

NO_SIGNATURE = "no-signature"

# Tokens that identify a failure rather than describe it.
PATTERNS = (
    re.compile(r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception|Failure|Fault))\b"),   # NameError
    re.compile(r"\b(?:HTTP\s*)?([1-5][0-9]{2})\b(?=\s|$|[.,:;)])"),             # 401
    re.compile(r"\b([A-Za-z0-9_./-]+\.(?:py|js|ts|go|java|rb|rs|sql))\b"),      # a file
    re.compile(r"\b([A-Z]{2,}[-_][A-Z0-9]{2,}(?:[-_][A-Z0-9]+)*)\b"),           # AUTH-401-TOKEN
    re.compile(r"\b(E[0-9]{3,}|SQLSTATE\s*[0-9A-Z]{5})\b"),                     # error codes
)

# Words that look identifying and are not. "Error" alone says nothing about which.
NOISE = {"ERROR", "FAILED", "FAILURE", "EXCEPTION", "FAULT", "TEST", "ASSERT"}


def derive(message):
    """A signature from free text, or NO_SIGNATURE when nothing identifying is there."""
    if not message:
        return NO_SIGNATURE
    found = []
    for pattern in PATTERNS:
        for m in pattern.findall(message):
            token = str(m).strip()
            if token and token.upper() not in NOISE and token not in found:
                found.append(token)
    if not found:
        return NO_SIGNATURE
    # Order-independent: the same facts stated in a different order are the same
    # failure, and a reworded report should not read as a new one.
    return "auto:" + hashlib.sha1("|".join(sorted(found)).encode()).hexdigest()[:12]


def identity(failure_class=None, signature=None, message=None):
    """The (class, signature) pair the loop compares."""
    cls = failure_class if failure_class in CLASSES else "unknown"
    sig = (signature or "").strip() or derive(message)
    return cls, sig


def same(a, b):
    """Are these the same failure?

    NO_SIGNATURE never matches, including itself: two failures nobody could
    identify are not evidence of repetition, and treating them as such would
    escalate on the strength of two uninformative reports.
    """
    if not a or not b:
        return False
    (ca, sa), (cb, sb) = a, b
    if sa == NO_SIGNATURE or sb == NO_SIGNATURE:
        return False
    return ca == cb and sa == sb


def describe(pair):
    cls, sig = pair
    return "%s/%s" % (cls, sig)
