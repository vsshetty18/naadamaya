"""
NAADAMAYA analyses and everything a report is made of.

Tables in this file:
  Analysis          one attempt: status, progress, overall score
  AnalysisMetric    one row per metric THIS analysis measured (or could not)
  AnalysisSection   per-section scores for the song timeline
  Insight           strengths and weaknesses found in the audio
  Recommendation    practice steps derived from the weakest areas
  AnalysisTimeline  the pitch curves and other dense arrays (one JSONB row)

Honesty rules built into the schema:
  - A metric that could not be measured gets available=false, score=NULL and
    an unavailable_reason. It is never given a made-up score.
  - `is_simulated` is true for every result produced in ANALYSIS_MODE=mock, so
    simulated data can always be told apart from real analysis.
  - overall_score is NULL until the analysis completes.

Idempotency: (user_id, idempotency_key) is UNIQUE, so a double-tapped REPORT
button or a retried request cannot start two analyses or spend two credits.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import AnalysisStage, AnalysisStatus


class Analysis(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "analyses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    song_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    recording_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=AnalysisStatus.QUEUED.value)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default=AnalysisStage.QUEUED.value)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 to 100

    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status_label: Mapped[str | None] = mapped_column(String(60), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    analysis_version: Mapped[str] = mapped_column(String(20), nullable=False)
    analysis_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="real")  # "real" | "mock"
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Everything else a report may contain and the frontend renders only when present:
    # song_profile, comparison snapshot rows, rhythm / pronunciation / breath blocks,
    # the "How you performed" list, pitch statistics.
    report_extras: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Credit handling (see credit_service): reserved when queued, refunded on server failure.
    credit_reserved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credit_refunded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(60), nullable=True)

    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)  # safe for users, no internals

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metrics: Mapped[list["AnalysisMetric"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="AnalysisMetric.position"
    )
    sections: Mapped[list["AnalysisSection"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="AnalysisSection.start_time"
    )
    insights: Mapped[list["Insight"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="Insight.priority"
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="Recommendation.priority"
    )
    timeline: Mapped["AnalysisTimeline | None"] = relationship(
        back_populates="analysis", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_analyses_user_idempotency_key"),
        Index("ix_analyses_user_id_created_at", "user_id", "created_at"),
        Index("ix_analyses_song_id_user_id", "song_id", "user_id"),
        Index("ix_analyses_recording_id", "recording_id"),
        Index("ix_analyses_status", "status"),
    )


class AnalysisMetric(UUIDMixin, Base):
    __tablename__ = "analysis_metrics"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )

    # Stable id the frontend maps to an icon and colour: "pitch_accuracy", "rhythm", ...
    metric_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)

    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # NULL when unavailable
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # MetricStatus
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)  # configured weight
    effective_weight: Mapped[float | None] = mapped_column(Float, nullable=True)  # after re-normalising
    relevance: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")  # high|medium|low
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    analysis: Mapped["Analysis"] = relationship(back_populates="metrics")

    __table_args__ = (
        UniqueConstraint("analysis_id", "metric_type", name="uq_analysis_metrics_analysis_metric"),
        Index("ix_analysis_metrics_analysis_id", "analysis_id"),
    )


class AnalysisSection(UUIDMixin, Base):
    __tablename__ = "analysis_sections"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )

    section_key: Mapped[str] = mapped_column(String(40), nullable=False)  # "verse_1", "chorus", ...
    section_name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)  # seconds
    end_time: Mapped[float] = mapped_column(Float, nullable=False)

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pitch_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    timing_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    stability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="good")  # good|warning|critical
    issues: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # [{"type","label"}]
    note: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # True when sections came from a fixed-length split because no reliable
    # structure could be detected. The report says so.
    is_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    analysis: Mapped["Analysis"] = relationship(back_populates="sections")

    __table_args__ = (Index("ix_analysis_sections_analysis_id", "analysis_id"),)


class Insight(UUIDMixin, Base):
    __tablename__ = "insights"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )

    type: Mapped[str] = mapped_column(String(20), nullable=False)  # InsightType
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # What measurement produced this insight. Proves it came from evidence.
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    analysis: Mapped["Analysis"] = relationship(back_populates="insights")

    __table_args__ = (Index("ix_insights_analysis_id", "analysis_id"),)


class Recommendation(UUIDMixin, Base):
    __tablename__ = "recommendations"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 1 = most important
    metric_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    section_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    analysis: Mapped["Analysis"] = relationship(back_populates="recommendations")

    __table_args__ = (Index("ix_recommendations_analysis_id", "analysis_id"),)


class AnalysisTimeline(UUIDMixin, Base):
    """
    Dense arrays for the graphs. One JSONB row per analysis instead of
    thousands of tiny rows.

    pitch_points: [{"t": 2.31, "ref_hz": 261.63, "user_hz": 248.21,
                    "ref_midi": 60.0, "user_midi": 59.1,
                    "deviation_cents": -91, "confidence": 0.92}, ...]
    annotations:  [{"startTime", "endTime", "type": "sharp|flat|unstable",
                    "cents", "label"}, ...]
    """

    __tablename__ = "analysis_timelines"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    pitch_points: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    annotations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reference_waveform: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # peaks 0..1
    user_waveform: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    analysis: Mapped["Analysis"] = relationship(back_populates="timeline")
