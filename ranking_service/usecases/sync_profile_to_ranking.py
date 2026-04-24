from dataclasses import dataclass
from typing import final

import structlog

from external_clients.profile_api.v1.profile_grpc import ProfileServiceStub
from external_clients.profile_api.v1.profile_pb2 import (
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_PREF_ANY,
    GENDER_PREF_FEMALE,
    GENDER_PREF_MALE,
    GetPreferencesRequest,
    GetProfileRequest,
)
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol
from ranking_service.usecases.calc_combined.usecase import CalcCombinedScore
from ranking_service.usecases.calc_primary.usecase import CalcPrimaryScore

log = structlog.stdlib.get_logger("ranking_service.usecases.SyncProfileToRanking")


@final
class SyncProfileToRanking[SessionT]:
    def __init__(
        self,
        *,
        profile_stub: ProfileServiceStub,
        rating_repository: RatingRepositoryProtocol[SessionT],
        calc_primary_score: CalcPrimaryScore[SessionT],
        calc_combined_score: CalcCombinedScore[SessionT],
    ) -> None:
        self._profile_stub = profile_stub
        self._rating_repository = rating_repository
        self._calc_primary_score = calc_primary_score
        self._calc_combined_score = calc_combined_score

    @dataclass
    class Request:
        telegram_id: int

    async def execute(self, request: Request) -> bool:
        profile = await self._profile_stub.GetProfile(GetProfileRequest(telegram_id=request.telegram_id))
        if not profile.found:
            log.warning("profile not found during ranking sync", telegram_id=request.telegram_id)
            return False

        preferences = await self._profile_stub.GetPreferences(GetPreferencesRequest(telegram_id=request.telegram_id))
        active_photos = sum(1 for photo in profile.photos if photo.is_active)

        completeness = float(
            bool(profile.name)
            + bool(profile.bio)
            + bool(profile.city)
            + bool(profile.age)
            + (profile.gender in (GENDER_MALE, GENDER_FEMALE))
            + (profile.HasField("latitude") and profile.HasField("longitude"))
        )
        photos_score = min(float(active_photos), 3.0)
        prefs_score = 1.0 if preferences.found else 0.0
        gender = {GENDER_MALE: "male", GENDER_FEMALE: "female"}.get(profile.gender)

        primary = await self._calc_primary_score.execute(
            CalcPrimaryScore.Request(
                telegram_id=request.telegram_id,
                completeness=completeness,
                photos=photos_score,
                prefs=prefs_score,
                verification=0.0,
                ai_quality=1.0,
                latitude=profile.latitude if profile.HasField("latitude") else None,
                longitude=profile.longitude if profile.HasField("longitude") else None,
                age=profile.age or None,
                gender=gender,
            )
        )

        async with self._rating_repository.context() as session:
            behavioral = await self._rating_repository.get_behavioral_rating(session, request.telegram_id)

        _ = await self._calc_combined_score.execute(
            CalcCombinedScore.Request(
                telegram_id=request.telegram_id,
                primary_score=primary.primary_rating.score,
                behavioral_score=behavioral.engagement_score if behavioral is not None else 0.0,
            )
        )

        log.info(
            "profile synced to ranking",
            telegram_id=request.telegram_id,
            active_photos=active_photos,
            preferences_found=preferences.found,
        )
        return True


def map_gender_pref_to_domain(pref: int) -> str | None:
    return {
        GENDER_PREF_MALE: "male",
        GENDER_PREF_FEMALE: "female",
        GENDER_PREF_ANY: "any",
    }.get(pref)
