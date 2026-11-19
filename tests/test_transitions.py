import pytest

from app.domain.enums import ActionStatus, DefectStatus, LotStatus, ReviewStatus
from app.domain.transitions import InvalidTransition, check


@pytest.mark.parametrize(
    "current,target",
    [
        (DefectStatus.CANDIDATE, DefectStatus.CONFIRMED),
        (DefectStatus.CANDIDATE, DefectStatus.REJECTED),
        (ReviewStatus.PENDING, ReviewStatus.DONE),
        (ActionStatus.OPEN, ActionStatus.IN_PROGRESS),
        (ActionStatus.IN_PROGRESS, ActionStatus.DONE),
        (ActionStatus.OPEN, ActionStatus.CANCELLED),
        (LotStatus.OPEN, LotStatus.ON_HOLD),
        (LotStatus.ON_HOLD, LotStatus.RELEASED),
        (LotStatus.ON_HOLD, LotStatus.SCRAPPED),
    ],
)
def test_allowed(current, target):
    check(current, target)


@pytest.mark.parametrize(
    "current,target",
    [
        (DefectStatus.CONFIRMED, DefectStatus.REJECTED),  # decisions are final; correct via a new event
        (DefectStatus.REJECTED, DefectStatus.CANDIDATE),
        (ReviewStatus.DONE, ReviewStatus.PENDING),
        (ActionStatus.OPEN, ActionStatus.DONE),  # must pass through in_progress
        (ActionStatus.DONE, ActionStatus.OPEN),
        (LotStatus.OPEN, LotStatus.RELEASED),  # only a held lot can be released
        (LotStatus.SCRAPPED, LotStatus.OPEN),
    ],
)
def test_rejected(current, target):
    with pytest.raises(InvalidTransition):
        check(current, target)
