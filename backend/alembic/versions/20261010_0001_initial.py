"""initial schema and default plans

Revision ID: 0001
Revises:
Create Date: 2026-10-10
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text("now()")


def ts(name, nullable=False, default=False):
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=NOW if default else None,
    )


def id_col():
    return sa.Column("id", UUID(as_uuid=True), nullable=False)


def created_updated():
    return [ts("created_at", default=True), ts("updated_at", default=True)]


def fk(table, column, target, ondelete):
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=f"fk_{table}_{column}_{target}", ondelete=ondelete
    )


def pk(table):
    return sa.PrimaryKeyConstraint("id", name=f"pk_{table}")


def uq(table, *cols, name=None):
    return sa.UniqueConstraint(*cols, name=name or f"uq_{table}_{cols[0]}")


def upgrade() -> None:
    # ---------------- users ----------------
    op.create_table(
        "users",
        id_col(),
        *created_updated(),
        sa.Column("phone_number_normalized", sa.String(20), nullable=False),
        sa.Column("phone_number", sa.String(20), nullable=False),
        sa.Column("phone_verified", sa.Boolean, nullable=False),
        sa.Column("phone_region", sa.String(4)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("is_deleted", sa.Boolean, nullable=False),
        ts("last_login_at", True),
        ts("last_seen_at", True),
        ts("deleted_at", True),
        pk("users"),
        uq("users", "phone_number_normalized"),
    )
    op.create_index("ix_users_status", "users", ["status"])
    op.create_index("ix_users_created_at", "users", ["created_at"])

    # ---------------- profiles ----------------
    op.create_table(
        "profiles",
        id_col(),
        *created_updated(),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(80)),
        sa.Column("username", sa.String(40)),
        sa.Column("email", sa.String(254)),
        sa.Column("profile_photo_key", sa.String(500)),
        sa.Column("gender", sa.String(30)),
        sa.Column("preferred_language", sa.String(30)),
        sa.Column("preferred_languages", JSONB, nullable=False),
        sa.Column("preferred_genres", JSONB, nullable=False),
        sa.Column("preferred_music_style", sa.String(40)),
        sa.Column("experience_level", sa.String(30)),
        sa.Column("vocal_range_low", sa.String(8)),
        sa.Column("vocal_range_high", sa.String(8)),
        sa.Column("vocal_range_source", sa.String(20)),
        sa.Column("onboarding_completed", sa.Boolean, nullable=False),
        pk("profiles"),
        fk("profiles", "user_id", "users", "CASCADE"),
        uq("profiles", "user_id"),
        uq("profiles", "username"),
    )

    # ---------------- otp_codes ----------------
    op.create_table(
        "otp_codes",
        id_col(),
        sa.Column("phone_number_normalized", sa.String(20), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        ts("expires_at"),
        sa.Column("attempt_count", sa.Integer, nullable=False),
        ts("verified_at", True),
        ts("invalidated_at", True),
        sa.Column("requested_ip", sa.String(45)),
        sa.Column("requested_device", sa.String(120)),
        sa.Column("provider", sa.String(20)),
        ts("created_at", default=True),
        pk("otp_codes"),
    )
    op.create_index(
        "ix_otp_codes_phone_purpose_created",
        "otp_codes",
        ["phone_number_normalized", "purpose", "created_at"],
    )
    op.create_index("ix_otp_codes_requested_ip_created", "otp_codes", ["requested_ip", "created_at"])
    op.create_index("ix_otp_codes_expires_at", "otp_codes", ["expires_at"])

    # ---------------- refresh_tokens ----------------
    op.create_table(
        "refresh_tokens",
        id_col(),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        ts("expires_at"),
        ts("revoked_at", True),
        sa.Column("replaced_by_id", UUID(as_uuid=True)),
        ts("last_used_at", True),
        sa.Column("created_ip", sa.String(45)),
        sa.Column("user_agent", sa.String(300)),
        sa.Column("device_label", sa.String(120)),
        ts("created_at", default=True),
        pk("refresh_tokens"),
        fk("refresh_tokens", "user_id", "users", "CASCADE"),
        uq("refresh_tokens", "token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    # ---------------- plans ----------------
    op.create_table(
        "plans",
        id_col(),
        *created_updated(),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("tagline", sa.String(160)),
        sa.Column("description", sa.Text),
        sa.Column("price_amount", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("billing_period", sa.String(20), nullable=False),
        sa.Column("monthly_limit", sa.Integer, nullable=False),
        sa.Column("period_days", sa.Integer, nullable=False),
        sa.Column("features", JSONB, nullable=False),
        sa.Column("feature_flags", JSONB, nullable=False),
        sa.Column("razorpay_plan_id", sa.String(60)),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("is_popular", sa.Boolean, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        pk("plans"),
        uq("plans", "code"),
    )
    op.create_index("ix_plans_is_active_rank", "plans", ["is_active", "rank"])

    # ---------------- subscriptions ----------------
    op.create_table(
        "subscriptions",
        id_col(),
        *created_updated(),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        ts("start_date"),
        ts("end_date", True),
        ts("renewal_date", True),
        ts("cancelled_at", True),
        sa.Column("credits_per_period", sa.Integer, nullable=False),
        ts("period_start"),
        ts("period_end", True),
        sa.Column("razorpay_subscription_id", sa.String(60)),
        pk("subscriptions"),
        fk("subscriptions", "user_id", "users", "CASCADE"),
        fk("subscriptions", "plan_id", "plans", "RESTRICT"),
        uq("subscriptions", "razorpay_subscription_id"),
    )
    op.create_index("ix_subscriptions_user_id_status", "subscriptions", ["user_id", "status"])
    op.create_index("ix_subscriptions_end_date", "subscriptions", ["end_date"])
    op.create_index(
        "uq_subscriptions_one_active_per_user",
        "subscriptions",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # ---------------- payments ----------------
    op.create_table(
        "payments",
        id_col(),
        *created_updated(),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", UUID(as_uuid=True), nullable=False),
        sa.Column("razorpay_order_id", sa.String(60), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(60)),
        sa.Column("razorpay_signature", sa.String(128)),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("method", sa.String(30)),
        sa.Column("failure_reason", sa.Text),
        ts("verified_at", True),
        ts("fulfilled_at", True),
        sa.Column("gateway_data", JSONB, nullable=False),
        pk("payments"),
        fk("payments", "user_id", "users", "RESTRICT"),
        fk("payments", "plan_id", "plans", "RESTRICT"),
        uq("payments", "razorpay_order_id"),
        uq("payments", "razorpay_payment_id"),
    )
    op.create_index("ix_payments_user_id_created_at", "payments", ["user_id", "created_at"])
    op.create_index("ix_payments_status", "payments", ["status"])

    # ---------------- webhook_events ----------------
    op.create_table(
        "webhook_events",
        id_col(),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("payload", JSONB, nullable=False),
        ts("received_at", default=True),
        ts("processed_at", True),
        pk("webhook_events"),
        uq("webhook_events", "event_id"),
    )
    op.create_index("ix_webhook_events_status", "webhook_events", ["status"])
    op.create_index(
        "ix_webhook_events_event_type_received", "webhook_events", ["event_type", "received_at"]
    )

    # ---------------- credit_transactions ----------------
    op.create_table(
        "credit_transactions",
        id_col(),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", UUID(as_uuid=True)),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column("reference_id", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        ts("period_start", True),
        ts("created_at", default=True),
        pk("credit_transactions"),
        fk("credit_transactions", "user_id", "users", "RESTRICT"),
        fk("credit_transactions", "subscription_id", "subscriptions", "SET NULL"),
        uq("credit_transactions", "idempotency_key"),
    )
    op.create_index(
        "ix_credit_transactions_user_id_created_at", "credit_transactions", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_credit_transactions_user_id_period", "credit_transactions", ["user_id", "period_start"]
    )
    op.create_index("ix_credit_transactions_reference_id", "credit_transactions", ["reference_id"])

    # ---------------- songs ----------------
    op.create_table(
        "songs",
        id_col(),
        *created_updated(),
        sa.Column("owner_id", UUID(as_uuid=True)),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("artist", sa.String(160)),
        sa.Column("movie", sa.String(160)),
        sa.Column("language", sa.String(30)),
        sa.Column("genre", sa.String(60)),
        sa.Column("lyricist", sa.String(160)),
        sa.Column("composer", sa.String(160)),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("original_file_key", sa.String(500)),
        sa.Column("processed_file_key", sa.String(500)),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("file_size", sa.Integer),
        sa.Column("format", sa.String(20)),
        sa.Column("duration", sa.Float),
        sa.Column("sample_rate", sa.Integer),
        sa.Column("channels", sa.Integer),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("lyrics", sa.String),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("is_deleted", sa.Boolean, nullable=False),
        ts("deleted_at", True),
        pk("songs"),
        fk("songs", "owner_id", "users", "CASCADE"),
    )
    op.create_index("ix_songs_owner_id_created_at", "songs", ["owner_id", "created_at"])
    op.create_index("ix_songs_title", "songs", ["title"])

    # ---------------- recordings ----------------
    op.create_table(
        "recordings",
        id_col(),
        *created_updated(),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("song_id", UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("original_file_key", sa.String(500)),
        sa.Column("processed_file_key", sa.String(500)),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("file_size", sa.Integer),
        sa.Column("format", sa.String(20)),
        sa.Column("duration", sa.Float),
        sa.Column("sample_rate", sa.Integer),
        sa.Column("channels", sa.Integer),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("is_deleted", sa.Boolean, nullable=False),
        ts("deleted_at", True),
        pk("recordings"),
        fk("recordings", "user_id", "users", "CASCADE"),
        fk("recordings", "song_id", "songs", "CASCADE"),
        uq("recordings", "user_id", "song_id", "attempt_number", name="uq_recordings_user_song_attempt"),
    )
    op.create_index("ix_recordings_user_id_created_at", "recordings", ["user_id", "created_at"])
    op.create_index("ix_recordings_song_id", "recordings", ["song_id"])

    # ---------------- analyses ----------------
    op.create_table(
        "analyses",
        id_col(),
        *created_updated(),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("song_id", UUID(as_uuid=True), nullable=False),
        sa.Column("recording_id", UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("progress", sa.Integer, nullable=False),
        sa.Column("overall_score", sa.Float),
        sa.Column("status_label", sa.String(60)),
        sa.Column("summary", sa.Text),
        sa.Column("analysis_version", sa.String(20), nullable=False),
        sa.Column("analysis_mode", sa.String(10), nullable=False),
        sa.Column("is_simulated", sa.Boolean, nullable=False),
        sa.Column("report_extras", JSONB, nullable=False),
        sa.Column("credit_reserved", sa.Boolean, nullable=False),
        sa.Column("credit_refunded", sa.Boolean, nullable=False),
        sa.Column("idempotency_key", sa.String(100)),
        sa.Column("celery_task_id", sa.String(60)),
        ts("processing_started_at", True),
        ts("completed_at", True),
        sa.Column("error_code", sa.String(40)),
        sa.Column("error_message", sa.Text),
        sa.Column("is_deleted", sa.Boolean, nullable=False),
        ts("deleted_at", True),
        pk("analyses"),
        fk("analyses", "user_id", "users", "CASCADE"),
        fk("analyses", "song_id", "songs", "CASCADE"),
        fk("analyses", "recording_id", "recordings", "CASCADE"),
        uq("analyses", "user_id", "idempotency_key", name="uq_analyses_user_idempotency_key"),
    )
    op.create_index("ix_analyses_user_id_created_at", "analyses", ["user_id", "created_at"])
    op.create_index("ix_analyses_song_id_user_id", "analyses", ["song_id", "user_id"])
    op.create_index("ix_analyses_recording_id", "analyses", ["recording_id"])
    op.create_index("ix_analyses_status", "analyses", ["status"])

    # ---------------- analysis children ----------------
    op.create_table(
        "analysis_metrics",
        id_col(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=False),
        sa.Column("metric_type", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("available", sa.Boolean, nullable=False),
        sa.Column("score", sa.Float),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("weight", sa.Float),
        sa.Column("effective_weight", sa.Float),
        sa.Column("relevance", sa.String(10), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("unavailable_reason", sa.Text),
        sa.Column("position", sa.Integer, nullable=False),
        pk("analysis_metrics"),
        fk("analysis_metrics", "analysis_id", "analyses", "CASCADE"),
        uq("analysis_metrics", "analysis_id", "metric_type", name="uq_analysis_metrics_analysis_metric"),
    )
    op.create_index("ix_analysis_metrics_analysis_id", "analysis_metrics", ["analysis_id"])

    op.create_table(
        "analysis_sections",
        id_col(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=False),
        sa.Column("section_key", sa.String(40), nullable=False),
        sa.Column("section_name", sa.String(80), nullable=False),
        sa.Column("start_time", sa.Float, nullable=False),
        sa.Column("end_time", sa.Float, nullable=False),
        sa.Column("score", sa.Float),
        sa.Column("pitch_score", sa.Float),
        sa.Column("timing_score", sa.Float),
        sa.Column("stability_score", sa.Float),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("issues", JSONB, nullable=False),
        sa.Column("note", sa.String(80)),
        sa.Column("is_estimated", sa.Boolean, nullable=False),
        pk("analysis_sections"),
        fk("analysis_sections", "analysis_id", "analyses", "CASCADE"),
    )
    op.create_index("ix_analysis_sections_analysis_id", "analysis_sections", ["analysis_id"])

    op.create_table(
        "insights",
        id_col(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        pk("insights"),
        fk("insights", "analysis_id", "analyses", "CASCADE"),
    )
    op.create_index("ix_insights_analysis_id", "insights", ["analysis_id"])

    op.create_table(
        "recommendations",
        id_col(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("metric_type", sa.String(40)),
        sa.Column("section_key", sa.String(40)),
        sa.Column("duration_minutes", sa.Integer),
        pk("recommendations"),
        fk("recommendations", "analysis_id", "analyses", "CASCADE"),
    )
    op.create_index("ix_recommendations_analysis_id", "recommendations", ["analysis_id"])

    op.create_table(
        "analysis_timelines",
        id_col(),
        sa.Column("analysis_id", UUID(as_uuid=True), nullable=False),
        sa.Column("pitch_points", JSONB, nullable=False),
        sa.Column("annotations", JSONB, nullable=False),
        sa.Column("reference_waveform", JSONB, nullable=False),
        sa.Column("user_waveform", JSONB, nullable=False),
        pk("analysis_timelines"),
        fk("analysis_timelines", "analysis_id", "analyses", "CASCADE"),
        uq("analysis_timelines", "analysis_id"),
    )

    _seed_plans()


def _seed_plans() -> None:
    """Starting plans, worded like the frontend. Edit prices later in the database."""
    plans = sa.table(
        "plans",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("tagline", sa.String),
        sa.column("price_amount", sa.Integer),
        sa.column("currency", sa.String),
        sa.column("billing_period", sa.String),
        sa.column("monthly_limit", sa.Integer),
        sa.column("period_days", sa.Integer),
        sa.column("features", JSONB),
        sa.column("feature_flags", JSONB),
        sa.column("rank", sa.Integer),
        sa.column("is_popular", sa.Boolean),
        sa.column("is_active", sa.Boolean),
    )

    def f(text, included=True):
        return {"text": text, "included": included}

    base = {"currency": "INR", "billing_period": "monthly", "period_days": 30, "is_active": True}
    op.bulk_insert(
        plans,
        [
            {
                **base, "id": uuid.uuid4(), "code": "FREE", "name": "Free",
                "tagline": "Get started on your musical journey.",
                "price_amount": 0, "monthly_limit": 10, "rank": 0, "is_popular": False,
                "features": [f("10 analysis credits"), f("Basic comparison report"), f("Standard analysis"),
                             f("Advanced insights", False), f("Priority processing", False), f("AI suggestions", False)],
                "feature_flags": {"advanced_insights": False, "priority_processing": False, "ai_suggestions": False},
            },
            {
                **base, "id": uuid.uuid4(), "code": "GO", "name": "Go",
                "tagline": "For consistent learners who want to grow more.",
                "price_amount": 19900, "monthly_limit": 30, "rank": 1, "is_popular": False,
                "features": [f("30 analysis credits"), f("Detailed comparison report"), f("Advanced analysis"),
                             f("AI suggestions"), f("Priority processing", False), f("Early access to new features", False)],
                "feature_flags": {"advanced_insights": True, "priority_processing": False, "ai_suggestions": True},
            },
            {
                **base, "id": uuid.uuid4(), "code": "PRO", "name": "Pro",
                "tagline": "For serious singers ready to go beyond.",
                "price_amount": 44900, "monthly_limit": 100, "rank": 2, "is_popular": True,
                "features": [f("100 analysis credits"), f("Complete AI report"), f("Advanced insights & tips"),
                             f("Priority processing"), f("Early access to new features"), f("Support & community access")],
                "feature_flags": {"advanced_insights": True, "priority_processing": True,
                                  "ai_suggestions": True, "early_access": True},
            },
        ],
    )


def downgrade() -> None:
    for table in (
        "analysis_timelines", "recommendations", "insights", "analysis_sections", "analysis_metrics",
        "analyses", "recordings", "songs", "credit_transactions", "webhook_events", "payments",
        "subscriptions", "plans", "refresh_tokens", "otp_codes", "profiles", "users",
    ):
        op.drop_table(table)
