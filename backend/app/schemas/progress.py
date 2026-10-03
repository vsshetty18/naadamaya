"""
NAADAMAYA progress schemas (attempt history and improvement over time).

Routes:
    GET /progress/history          (paginated)  -> Page[AttemptEntry]
    GET /progress/songs/{song_id}               -> SongProgress
    GET /progress                               -> ProgressOverview

Every number is computed from the user's own completed analyses in the
database. Nothing is hardcoded, and a user with no attempts gets zeros and
empty lists, never invented figures.

Frontend mapping:
    Attempt History chart  <- SongProgress.history  [{attempt, score, date}]
    Stage statistics       <- ProgressOverview.songs_practiced / songs_recorded
"""

import uuid
from datetime import date, datetime

from pydantic import Field

from app.schemas.common import APIModel


class AttemptEntry(APIModel):
    """One completed analysis, as a point in the user's history."""

    analysis_id: uuid.UUID
    song_id: uuid.UUID
    song_title: str | None = None
    attempt: int = Field(description="This user's attempt number for this song.")
    score: float | None = None
    date: datetime
    is_simulated: bool = False
    strengths: list[str] = Field(default_factory=list, description="Titles of positive insights.")
    improvements: list[str] = Field(default_factory=list, description="Titles of improvement insights.")


class WeakArea(APIModel):
    metric_id: str = Field(examples=["stability"])
    name: str = Field(examples=["Stability"])
    average_score: float = Field(description="Average over the recent attempts that measured it.")
    attempts_measured: int


class SongProgress(APIModel):
    song_id: uuid.UUID
    song_title: str | None = None
    song_artist: str | None = None

    attempt_count: int = 0
    latest_score: float | None = None
    best_score: float | None = None
    first_score: float | None = None
    improvement: float | None = Field(
        default=None, description="Latest minus first score. Null with fewer than 2 attempts."
    )
    improvement_percent: float | None = None
    trend: str = Field(default="flat", description="up | down | flat")

    history: list[AttemptEntry] = Field(default_factory=list)
    weak_areas: list[WeakArea] = Field(
        default_factory=list, description="Lowest-scoring metrics across recent attempts."
    )


class SongSummary(APIModel):
    song_id: uuid.UUID
    song_title: str | None = None
    attempt_count: int
    latest_score: float | None = None
    best_score: float | None = None
    last_attempt_at: datetime | None = None


class ProgressOverview(APIModel):
    total_analyses: int = 0
    songs_practiced: int = Field(default=0, description="Distinct songs with a completed analysis.")
    songs_recorded: int = Field(default=0, description="Recordings made in the app (not uploaded).")
    total_recordings: int = 0

    average_score: float | None = None
    best_score: float | None = None
    improvement_percent: float | None = Field(
        default=None, description="Average of recent attempts vs. earlier ones. Null if too few."
    )

    current_streak_days: int = Field(default=0, description="Consecutive days with a completed analysis.")
    longest_streak_days: int = 0
    last_practice_date: date | None = None

    songs: list[SongSummary] = Field(default_factory=list)
    weak_areas: list[WeakArea] = Field(default_factory=list)
