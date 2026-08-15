"""The screening entity. Answers are sensitive, so none of these assert on what was
answered beyond what the rule under test needs."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.errors import InvalidScreeningError
from app.domain.screening import QUESTION_KEYS, QUESTIONS, Screening

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)
ALICE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def answers(**overrides: bool) -> dict[str, bool]:
    complete = dict.fromkeys(QUESTION_KEYS, False)
    complete.update(overrides)
    return complete


def build(**kwargs: object) -> Screening:
    defaults: dict[str, object] = {
        "member_id": ALICE,
        "answers": answers(),
        "risk_acknowledged": True,
        "screened_on": date(2026, 8, 16),
        "now": NOW,
    }
    defaults.update(kwargs)
    return Screening.create(**defaults)  # type: ignore[arg-type]


def test_there_are_eleven_questions_in_three_groups() -> None:
    """The instrument's shape, pinned: a question dropped by accident would silently
    stop being asked."""
    assert len(QUESTIONS) == 11
    assert len(QUESTION_KEYS) == 11
    assert len({group for _, group in QUESTIONS}) == 3


def test_a_missing_answer_is_refused_rather_than_read_as_no() -> None:
    """The failure this exists to prevent: an unanswered cardiac question treated as a
    clean result (golden rule #4 — an unknown is never filled in)."""
    incomplete = answers()
    del incomplete["heart_condition"]

    with pytest.raises(InvalidScreeningError, match="heart_condition"):
        build(answers=incomplete)


def test_an_unknown_question_is_refused() -> None:
    """A client sending a key we do not know is either out of date or making things up;
    storing it would put an answer in the record that nothing can interpret."""
    with pytest.raises(InvalidScreeningError, match="favourite_colour"):
        build(answers=answers() | {"favourite_colour": True})


def test_a_non_boolean_answer_is_refused() -> None:
    with pytest.raises(InvalidScreeningError):
        build(answers=answers() | {"diabetes": "yes"})


def test_all_no_needs_no_medical_advice() -> None:
    screening = build()

    assert screening.yes_count == 0
    assert screening.needs_medical_advice is False


def test_a_single_yes_is_enough_to_advise() -> None:
    """The instrument catches the one condition that matters; it is not a score to be
    outweighed by ten reassuring answers."""
    screening = build(answers=answers(chest_pain_at_rest=True))

    assert screening.yes_count == 1
    assert screening.needs_medical_advice is True


def test_answers_are_stored_in_question_order() -> None:
    """So a stored record reads the same way every time, whatever order a client sent."""
    shuffled = dict(reversed(list(answers().items())))

    stored = build(answers=shuffled)

    assert list(stored.answers) == [key for key, _ in QUESTIONS]


def test_screening_in_the_future_is_refused() -> None:
    with pytest.raises(InvalidScreeningError, match="future"):
        build(screened_on=date(2026, 8, 17))


def test_screening_today_is_allowed() -> None:
    build(screened_on=NOW.date())


def test_answering_again_keeps_the_same_row() -> None:
    """One record per member: the club needs what is true now, and keeping every past
    draft of someone's cardiac history is a liability rather than an asset."""
    first = build()
    later = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)

    revised = Screening.create(
        member_id=ALICE,
        answers=answers(diabetes=True),
        risk_acknowledged=True,
        screened_on=date(2026, 9, 1),
        now=later,
        existing=first,
    )

    assert revised.id == first.id
    assert revised.created_at == first.created_at
    assert revised.updated_at == later
    assert revised.needs_medical_advice is True


def test_a_first_screening_gets_its_own_id() -> None:
    assert build().id != build().id


def test_the_version_is_recorded() -> None:
    """So a future revision of the instrument does not silently change what an old
    member's answers meant."""
    assert build().version == "parq-plus-th-v1"


def test_it_belongs_to_the_member_it_was_built_for() -> None:
    other = uuid4()

    assert build(member_id=other).member_id == other
