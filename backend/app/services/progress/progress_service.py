"""
NAADAMAYA progress tracking.

    overview = get_overview(db, user_id)             # GET /progress
    song     = get_song_progress(db, user_id, id)    # GET /progress/songs/{song_id}
    page     = list_history(db, user_id, params)     # GET /progress/history

Everything is computed from the user's own COMPLETED, non-deleted analyses.
Nothing is stored separately and nothing is invented: a new user gets zeros,
empty lists and None for anything that needs more data (for example
improvement needs at least two attempts).

Ownership: every query filters on user_id.
"""

import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.analysis import Analysis
from app.models.enums import AnalysisStatus
from app.models.recording import Recording
from app.models.song import Song
from app.schemas.common import Page, PageParams
from app.schemas.progress import (
    AttemptEntry,
    ProgressOverview,
    SongProgress,
    SongSummary,
    WeakArea,
)

RECENT_ATTEMPTS = 5
MAX_WEAK_AREAS = 3
WEAK_BELOW = 80.0
FLAT_BAND = 1.0          # a change smaller than this counts as flat


def _completed(user_id: uuid.UUID):
    return (
        Analysis.user_id == user_id,
        Analysis.status == AnalysisStatus.COMPLETED.value,
        Analysis.is_deleted.is_(False),
    )


def _entry(a: Analysis, title: str | None) -> AttemptEntry:
    return AttemptEntry(
        analysis_id=a.id,
        song_id=a.song_id,
        song_title=title,
        attempt=a.attempt_number,
        score=a.overall_score,
        date=a.completed_at or a.created_at,
        is_simulated=a.is_simulated,
        strengths=[i.title for i in a.insights if i.type == "positive"][:3],
        improvements=[i.title for i in a.insights if i.type == "improvement"][:3],
    )


def _weak_areas(analyses: list[Analysis]) -> list[WeakArea]:
    """Lowest average metric scores over the given attempts. Unavailable metrics are ignored."""
    scores: dict[str, list[float]] = defaultdict(list)
    names: dict[str, str] = {}
    for a in analyses:
        for m in a.metrics:
            if m.available and m.score is not None:
                scores[m.metric_type].append(m.score)
                names[m.metric_type] = m.name
    rows = [
        WeakArea(
            metric_id=k,
            name=names[k],
            average_score=round(sum(v) / len(v), 1),
            attempts_measured=len(v),
        )
        for k, v in scores.items()
    ]
    rows = [r for r in rows if r.average_score < WEAK_BELOW]
    rows.sort(key=lambda r: r.average_score)
    return rows[:MAX_WEAK_AREAS]


def _trend(delta: float | None) -> str:
    if delta is None or abs(delta) < FLAT_BAND:
        return "flat"
    return "up" if delta > 0 else "down"


# ==========================================================
# One song
# ==========================================================
def get_song_progress(db: Session, user_id: uuid.UUID, song_id: uuid.UUID) -> SongProgress:
    song = db.get(Song, song_id)
    if song is None or song.is_deleted or (song.owner_id is not None and song.owner_id != user_id):
        raise NotFoundError("We could not find that song.")

    analyses = list(
        db.scalars(
            select(Analysis)
            .where(*_completed(user_id), Analysis.song_id == song_id)
            .order_by(Analysis.attempt_number)
        )
    )
    scored = [a.overall_score for a in analyses if a.overall_score is not None]

    first = scored[0] if scored else None
    latest = scored[-1] if scored else None
    improvement = round(latest - first, 1) if len(scored) >= 2 else None
    percent = (
        round(100.0 * improvement / first, 1)
        if improvement is not None and first and first > 0
        else None
    )

    return SongProgress(
        song_id=song.id,
        song_title=song.title,
        song_artist=song.artist,
        attempt_count=len(analyses),
        latest_score=latest,
        best_score=max(scored) if scored else None,
        first_score=first,
        improvement=improvement,
        improvement_percent=percent,
        trend=_trend(improvement),
        history=[_entry(a, song.title) for a in analyses],
        weak_areas=_weak_areas(analyses[-RECENT_ATTEMPTS:]),
    )


# ==========================================================
# Streaks
# ==========================================================
def _streaks(days: set[date], today: date) -> tuple[int, int]:
    """(current, longest) runs of consecutive practice days."""
    if not days:
        return 0, 0
    ordered = sorted(days)
    longest = run = 1
    for prev, cur in zip(ordered, ordered[1:]):
        run = run + 1 if cur - prev == timedelta(days=1) else 1
        longest = max(longest, run)

    # The streak is alive if the last practice was today or yesterday.
    current = 0
    if ordered[-1] >= today - timedelta(days=1):
        day = ordered[-1]
        while day in days:
            current += 1
            day -= timedelta(days=1)
    return current, longest


# ==========================================================
# Overview
# ==========================================================
def get_overview(db: Session, user_id: uuid.UUID, today: date | None = None) -> ProgressOverview:
    from app.core.security import utcnow

    today = today or utcnow().date()
    analyses = list(
        db.scalars(select(Analysis).where(*_completed(user_id)).order_by(Analysis.completed_at))
    )

    total_recordings = db.scalar(
        select(func.count()).select_from(Recording).where(
            Recording.user_id == user_id, Recording.is_deleted.is_(False)
        )
    ) or 0
    songs_recorded = db.scalar(
        select(func.count()).select_from(Recording).where(
            Recording.user_id == user_id,
            Recording.is_deleted.is_(False),
            Recording.source == "browser_recording",
        )
    ) or 0

    if not analyses:
        return ProgressOverview(total_recordings=total_recordings, songs_recorded=songs_recorded)

    titles = {
        s.id: s.title
        for s in db.scalars(select(Song).where(Song.id.in_({a.song_id for a in analyses})))
    }

    scores = [a.overall_score for a in analyses if a.overall_score is not None]
    average = round(sum(scores) / len(scores), 1) if scores else None

    # Improvement: average of the latest attempts against the earliest ones.
    improvement = None
    if len(scores) >= 4:
        half = len(scores) // 2
        early = sum(scores[:half]) / half
        late = sum(scores[-half:]) / half
        improvement = round(100.0 * (late - early) / early, 1) if early > 0 else None

    by_song: dict[uuid.UUID, list[Analysis]] = defaultdict(list)
    for a in analyses:
        by_song[a.song_id].append(a)

    songs = []
    for sid, items in by_song.items():
        vals = [x.overall_score for x in items if x.overall_score is not None]
        songs.append(
            SongSummary(
                song_id=sid,
                song_title=titles.get(sid),
                attempt_count=len(items),
                latest_score=vals[-1] if vals else None,
                best_score=max(vals) if vals else None,
                last_attempt_at=items[-1].completed_at or items[-1].created_at,
            )
        )
    songs.sort(key=lambda s: s.last_attempt_at or utcnow(), reverse=True)

    days = {(a.completed_at or a.created_at).date() for a in analyses}
    current, longest = _streaks(days, today)

    return ProgressOverview(
        total_analyses=len(analyses),
        songs_practiced=len(by_song),
        songs_recorded=songs_recorded,
        total_recordings=total_recordings,
        average_score=average,
        best_score=max(scores) if scores else None,
        improvement_percent=improvement,
        current_streak_days=current,
        longest_streak_days=longest,
        last_practice_date=max(days),
        songs=songs[:10],
        weak_areas=_weak_areas(analyses[-RECENT_ATTEMPTS:]),
    )


# ==========================================================
# History
# ==========================================================
def list_history(db: Session, user_id: uuid.UUID, params: PageParams) -> Page[AttemptEntry]:
    total = db.scalar(select(func.count()).select_from(Analysis).where(*_completed(user_id))) or 0
    rows = db.execute(
        select(Analysis, Song)
        .join(Song, Song.id == Analysis.song_id)
        .where(*_completed(user_id))
        .order_by(Analysis.completed_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    ).all()
    return Page.build([_entry(a, s.title) for a, s in rows], total, params)
