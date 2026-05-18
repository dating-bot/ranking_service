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
from ranking_service.infra.tracing import current_trace_id, inject_grpc_metadata
from ranking_service.protocols import ProfileInsightsProtocol
from ranking_service.protocols.rating.repository import RatingRepositoryProtocol
from ranking_service.usecases.calc_combined.usecase import CalcCombinedScore
from ranking_service.usecases.calc_primary.usecase import CalcPrimaryScore

log = structlog.stdlib.get_logger("ranking_service.usecases.SyncProfileToRanking")

COMPLETENESS_COMPONENT_POINTS = 5.0
MAX_PHOTOS_CONSIDERED = 3.0
MAX_PHOTOS_SCORE = 25.0
PREFERENCES_SCORE = 10.0


@final
class SyncProfileToRanking[SessionT]:
    def __init__(
        self,
        *,
        profile_stub: ProfileServiceStub,
        rating_repository: RatingRepositoryProtocol[SessionT],
        profile_insights: ProfileInsightsProtocol,
        calc_primary_score: CalcPrimaryScore[SessionT],
        calc_combined_score: CalcCombinedScore[SessionT],
    ) -> None:
        self._profile_stub = profile_stub
        self._rating_repository = rating_repository
        self._profile_insights = profile_insights
        self._calc_primary_score = calc_primary_score
        self._calc_combined_score = calc_combined_score

    @dataclass
    class Request:
        telegram_id: int
        trace_id: str | None = None

    async def execute(self, request: Request) -> bool:
        trace_id = request.trace_id or current_trace_id()
        metadata = inject_grpc_metadata([("trace_id", trace_id)] if trace_id else None)

        profile = await self._profile_stub.GetProfile(
            GetProfileRequest(telegram_id=request.telegram_id),
            metadata=metadata,
        )
        if not profile.found:
            log.warning("profile not found during ranking sync", telegram_id=request.telegram_id)
            return False

        preferences = await self._profile_stub.GetPreferences(
            GetPreferencesRequest(telegram_id=request.telegram_id),
            metadata=metadata,
        )
        active_photos = sum(1 for photo in profile.photos if photo.is_active)

        completeness_flags = float(
            bool(profile.name)
            + bool(profile.bio)
            + bool(profile.city)
            + bool(profile.age)
            + (profile.gender in (GENDER_MALE, GENDER_FEMALE))
            + (profile.HasField("latitude") and profile.HasField("longitude"))
        )
        completeness = completeness_flags * COMPLETENESS_COMPONENT_POINTS
        photos_score = min(float(active_photos), MAX_PHOTOS_CONSIDERED) / MAX_PHOTOS_CONSIDERED * MAX_PHOTOS_SCORE
        prefs_score = PREFERENCES_SCORE if preferences.found else 0.0
        gender = {GENDER_MALE: "male", GENDER_FEMALE: "female"}.get(profile.gender)
        ai_quality_raw = await self._profile_insights.get_ai_quality_score(request.telegram_id)
        ai_quality = _normalize_ai_quality(ai_quality_raw)
        verification_score = await self._profile_insights.get_verification_score(request.telegram_id)
        referral_score = await self._profile_insights.get_referral_score(request.telegram_id)
        semantic_bonus = await self._profile_insights.get_profile_semantic_bonus(request.telegram_id)
        profile_is_active = await self._profile_insights.get_profile_is_active(request.telegram_id)
        status = "active" if profile_is_active else "archived"

        primary = await self._calc_primary_score.execute(
            CalcPrimaryScore.Request(
                telegram_id=request.telegram_id,
                completeness=completeness,
                photos=photos_score,
                prefs=prefs_score,
                verification=verification_score,
                ai_quality=ai_quality,
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
                referral_score=referral_score,
                semantic_bonus=semantic_bonus,
                status=status,
            )
        )

        log.info(
            "profile synced to ranking",
            telegram_id=request.telegram_id,
            active_photos=active_photos,
            preferences_found=preferences.found,
            ai_quality_raw=ai_quality_raw,
            ai_quality_normalized=ai_quality,
            verification_score=verification_score,
            referral_score=referral_score,
            semantic_bonus=semantic_bonus,
            profile_is_active=profile_is_active,
            combined_status=status,
        )
        return True


def map_gender_pref_to_domain(pref: int) -> str | None:
    return {
        GENDER_PREF_MALE: "male",
        GENDER_PREF_FEMALE: "female",
        GENDER_PREF_ANY: "any",
    }.get(pref)


def _normalize_ai_quality(raw: float | None) -> float:
    if raw is None:
        return 1.0
    return max(0.0, min(10.0, float(raw))) / 10.0
