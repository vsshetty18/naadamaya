"""
NAADAMAYA enumerations.

Every enum is a `str` enum, so values serialise cleanly to JSON and are
stored in the database as plain strings (VARCHAR), not as PostgreSQL ENUM
types. That keeps future migrations simple: adding a new value never needs
an ALTER TYPE.
"""

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


# ---- Accounts ----
class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class UserRole(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"
    # Reserved for later: SUPPORT, ANALYST, SUPER_ADMIN


# ---- OTP ----
class OtpPurpose(StrEnum):
    LOGIN = "LOGIN"
    SIGNUP = "SIGNUP"
    PHONE_VERIFICATION = "PHONE_VERIFICATION"
    CHANGE_PHONE = "CHANGE_PHONE"
    PAYMENT_SECURITY = "PAYMENT_SECURITY"


# ---- Songs and recordings ----
class SourceType(StrEnum):
    UPLOAD = "UPLOAD"          # uploaded by the user as a reference
    CATALOG = "CATALOG"        # reserved for a future song catalogue


class RecordingKind(StrEnum):
    REFERENCE = "REFERENCE"    # the original song
    USER_VOCAL = "USER_VOCAL"  # the singer's own take


class RecordingStatus(StrEnum):
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


# ---- Analysis ----
class AnalysisStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AnalysisStage(StrEnum):
    QUEUED = "QUEUED"
    PREPROCESSING = "PREPROCESSING"
    ALIGNMENT = "ALIGNMENT"
    PITCH_ANALYSIS = "PITCH_ANALYSIS"
    RHYTHM_ANALYSIS = "RHYTHM_ANALYSIS"
    STABILITY_ANALYSIS = "STABILITY_ANALYSIS"
    SCORING = "SCORING"
    REPORT_GENERATION = "REPORT_GENERATION"
    COMPLETED = "COMPLETED"


class MetricStatus(StrEnum):
    EXCELLENT = "excellent"
    VERY_GOOD = "very_good"
    GOOD = "good"
    NEEDS_PRACTICE = "needs_practice"
    NEEDS_IMPROVEMENT = "needs_improvement"
    UNAVAILABLE = "unavailable"  # could not be measured reliably


class InsightType(StrEnum):
    POSITIVE = "positive"
    IMPROVEMENT = "improvement"
    NOTE = "note"


# ---- Payments and plans ----
class PaymentStatus(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class SubscriptionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    HALTED = "HALTED"


class CreditTransactionType(StrEnum):
    GRANT = "GRANT"            # monthly allowance or purchase
    CONSUME = "CONSUME"        # one analysis started
    REFUND = "REFUND"          # analysis failed on our side
    ADJUSTMENT = "ADJUSTMENT"  # manual change by an admin
