"""One accumulator owns precedence, messages and evidence for every rule.

Every rule in the pack follows the same five moves (see engine_core.py R003):
seed evidence, accumulate failures and unknowns, apply precedence, compose the
message, build the result. A rule author writes only the second move. Findings
does the other four, identically for all fifteen rules.

    f = Findings(ctx)
    for i, line in ctx.lines():
        p = ctx.path("lines", i, "service_date")
        f.cite(p)
        d = valid_date(line["service_date"])
        if d is None:
            f.unknown("service date")
        elif d > submitted:
            f.fail("service date after submission", p, line_id=line["line_id"])
    return f.verdict("All service dates are on or before submission.")
"""
from typing import List, NamedTuple, Optional, Sequence, Tuple

from .context import RuleContext


class Verdict(NamedTuple):
    status: str
    paths: Tuple[str, ...]
    message: str
    line_ids: Tuple[str, ...]


class Findings:
    """Collects what one rule observed on one claim."""

    def __init__(self, ctx: RuleContext, *, applicable: bool = True):
        """applicable=False for rules that apply only to some claims (R008,
        R009, R010). Call mark_applicable() once a line the rule governs is
        found; if none is, the verdict is NOT_APPLICABLE."""
        self.ctx = ctx
        self._paths: List[str] = []
        self._failures: List[str] = []
        self._unknowns: List[str] = []
        self._line_ids: List[str] = []
        self._applicable = applicable

    def cite(self, *paths: str) -> "Findings":
        """Record evidence paths regardless of outcome. Cite what you inspected,
        including fields whose value is None."""
        self._paths.extend(paths)
        return self

    def fail(self, reason: str, *paths: str, line_id: Optional[str] = None) -> "Findings":
        """A violation is proven by the supplied data. Pass line_id when the
        violation belongs to a specific line; take it from line["line_id"],
        never build it yourself. Claim-level failures pass no line_id."""
        self._failures.append(reason)
        self._paths.extend(paths)
        if line_id is not None:
            self._line_ids.append(line_id)
        self._applicable = True
        return self

    def unknown(self, reason: str, *paths: str) -> "Findings":
        """Information needed to decide is missing or unusable. Takes no
        line_id: in the gold data, UNABLE_TO_ASSESS never carries line IDs."""
        self._unknowns.append(reason)
        self._paths.extend(paths)
        self._applicable = True
        return self

    def mark_applicable(self) -> "Findings":
        """The rule governs at least one part of this claim."""
        self._applicable = True
        return self

    @property
    def failures(self) -> Tuple[str, ...]:
        """Distinct failure reasons, sorted."""
        return tuple(sorted(set(self._failures)))

    @property
    def unknowns(self) -> Tuple[str, ...]:
        """Distinct unknown reasons, sorted."""
        return tuple(sorted(set(self._unknowns)))

    def verdict(
        self,
        pass_message: str,
        *,
        not_applicable_message: Optional[str] = None,
        message: Optional[str] = None,
        fallback_evidence: Sequence[str] = (),
    ) -> Verdict:
        """Apply the rulebook's precedence and return the rule's outcome.

        Status, in order:
          any fail()        -> FAIL
          else any unknown()-> UNABLE_TO_ASSESS
          else not applicable -> NOT_APPLICABLE
          else              -> PASS

        Message, unless `message` overrides it for FAIL or UNABLE_TO_ASSESS:
          FAIL              "; ".join(failures), plus
                            "; Additional unknown inputs: " + ", ".join(unknowns)
                            when both exist. The rulebook requires uncertainty
                            to survive even when another line proves a failure.
          UNABLE_TO_ASSESS  "; ".join(unknowns)
          NOT_APPLICABLE    not_applicable_message (required)
          PASS              pass_message

        Evidence: every cited path, de-duplicated, in first-cited order. If no
        path was cited at all, fallback_evidence is used instead.

        Line IDs: failing lines only, de-duplicated, in claim line order.

        Guarantees (raises AssertionError otherwise), so the scorer cannot
        reject a result for these reasons:
          - status is one of the four rule statuses
          - the message is non-blank after strip()
          - at least one evidence path exists
          - every line ID belongs to this claim
        """
        raise NotImplementedError("Block C1: implement precedence and assertions")
