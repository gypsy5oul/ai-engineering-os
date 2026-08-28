"""Decide whether a record may be deleted.

One module, standard library only, no configuration surface and no abstraction
over the single policy that exists. The service answers one question and records
why it answered it that way, because a retention decision nobody can explain is
one nobody can defend.
"""
import datetime


class Record(object):
    """A record with a creation date, and possibly a legal hold."""

    __slots__ = ("id", "created_on", "on_legal_hold")

    def __init__(self, id, created_on, on_legal_hold=False):
        if not id:
            raise ValueError("a record with no id cannot be decided about")
        if not isinstance(created_on, datetime.date):
            raise ValueError("record %s: created_on must be a date, got %r"
                             % (id, type(created_on).__name__))
        self.id = id
        self.created_on = created_on
        self.on_legal_hold = bool(on_legal_hold)

    @classmethod
    def from_dict(cls, raw):
        """Parse one record. Raises rather than defaulting.

        A malformed record must never fall through to a permissive answer: the
        expensive mistake in this service is reporting something deletable that
        is not, and a lenient parser is the cheapest way to make it.
        """
        if not isinstance(raw, dict):
            raise ValueError("a record must be a mapping, got %r" % type(raw).__name__)
        missing = [k for k in ("id", "created_on") if k not in raw]
        if missing:
            raise ValueError("record is missing %s" % ", ".join(missing))
        created = raw["created_on"]
        if isinstance(created, str):
            try:
                y, m, d = (int(p) for p in created.split("-"))
                created = datetime.date(y, m, d)
            except (ValueError, TypeError):
                raise ValueError("record %s: created_on %r is not an ISO date"
                                 % (raw["id"], raw["created_on"]))
        return cls(raw["id"], created, raw.get("on_legal_hold", False))


class RetentionPolicy(object):
    """How long a record must be kept, in days."""

    __slots__ = ("retain_days",)

    def __init__(self, retain_days):
        if not isinstance(retain_days, int) or isinstance(retain_days, bool):
            raise ValueError("retain_days must be a whole number of days")
        if retain_days < 0:
            raise ValueError("retain_days cannot be negative")
        self.retain_days = retain_days


class Decision(object):
    """What was decided about one record, and the rule that decided it."""

    __slots__ = ("record_id", "deletable", "rule", "eligible_on")

    def __init__(self, record_id, deletable, rule, eligible_on):
        self.record_id = record_id
        self.deletable = deletable
        self.rule = rule
        self.eligible_on = eligible_on

    def as_dict(self):
        return {"record_id": self.record_id, "deletable": self.deletable,
                "rule": self.rule, "eligible_on": self.eligible_on.isoformat()}


def eligible_on(record, policy):
    """The first date the record may be deleted."""
    return record.created_on + datetime.timedelta(days=policy.retain_days)


def decide(record, policy, today):
    """Decide one record.

    Legal hold is checked first and short-circuits, because a hold outranks age:
    an expired record under hold is still not deletable, and checking age first
    would make the answer depend on the order of two independent facts.
    """
    due = eligible_on(record, policy)
    if record.on_legal_hold:
        return Decision(record.id, False, "legal-hold", due)
    if today < due:
        return Decision(record.id, False, "within-retention-window", due)
    return Decision(record.id, True, "retention-window-elapsed", due)


def decide_all(records, policy, today):
    return [decide(r, policy, today) for r in records]
