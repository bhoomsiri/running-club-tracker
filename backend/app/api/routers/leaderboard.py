"""The club standing. Every signed-in member may read it; nobody else.

Not public, unlike the announcements: a name next to a distance is ordinary personal
data, but putting who at the hospital runs how far in front of anyone who finds the URL
is not something the club has asked permission for.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import get_current_member_id, get_leaderboard_uc
from app.api.schemas import LeaderboardResponse
from app.application.use_cases.get_leaderboard import GetLeaderboard

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard", response_model=LeaderboardResponse)
def leaderboard(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[GetLeaderboard, Depends(get_leaderboard_uc)],
) -> LeaderboardResponse:
    # member_id comes from the token and is used only to mark which row is the caller's.
    return LeaderboardResponse.from_leaderboard(use_case.execute(member_id))
