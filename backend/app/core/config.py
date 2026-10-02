"""
NAADAMAYA application settings.

Every value comes from environment variables (see .env.example).
Nothing secret is hardcoded. In production the app refuses to start with
unsafe settings (mock OTP, mock analysis, debug on, placeholder secrets).
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = {
    "",
    "change-me-to-a-long-random-string",
    "change-me-to-another-long-random-string",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    app_name: str = "NAADAMAYA"
    environment: str = "development"  # development | staging | production
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    frontend_url: str = "http://localhost:5173"
    # Comma-separated. Kept as a string because env lists are awkward to parse.
    cors_origins: str = "http://localhost:5173"

    # ---- Database / Redis ----
    database_url: str = "postgresql+psycopg://naadamaya:naadamaya@db:5432/naadamaya"
    redis_url: str = "redis://redis:6379/0"

    # ---- Tokens ----
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 30
    token_hash_secret: str = ""

    # ---- OTP ----
    otp_mode: str = "development"  # development | production
    otp_provider: str = "mock"  # mock | msg91 | twilio
    otp_length: int = 6
    otp_expire_seconds: int = 300
    otp_resend_cooldown_seconds: int = 30
    otp_max_verify_attempts: int = 5
    otp_max_requests_per_hour: int = 5
    otp_dev_fixed_code: str = "123456"
    default_country_code: str = "IN"

    msg91_auth_key: str = ""
    msg91_template_id: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # ---- Razorpay ----
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # ---- Storage ----
    storage_provider: str = "local"  # local | s3
    storage_local_dir: str = "/data/uploads"
    storage_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = "auto"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    signed_url_expire_seconds: int = 600

    # ---- Uploads ----
    max_upload_size_mb: int = 50
    max_audio_duration_seconds: int = 900
    min_audio_duration_seconds: int = 3

    # ---- Analysis ----
    analysis_mode: str = "mock"  # mock | real
    analysis_version: str = "1.0.0"
    analysis_sample_rate: int = 22050

    # ---- Rate limits ----
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = 120
    rate_limit_otp_per_ip_per_hour: int = 20
    rate_limit_upload_per_minute: int = 10
    rate_limit_analysis_per_hour: int = 20

    # ---- Logging ----
    log_level: str = "INFO"

    # ------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def use_mock_analysis(self) -> bool:
        return self.analysis_mode.lower() == "mock"

    @property
    def otp_dev_mode(self) -> bool:
        """True only outside production AND when OTP_MODE=development."""
        return (not self.is_production) and self.otp_mode.lower() == "development"

    # ------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------
    @model_validator(mode="after")
    def _check_settings(self) -> "Settings":
        if self.analysis_mode.lower() not in {"mock", "real"}:
            raise ValueError("ANALYSIS_MODE must be 'mock' or 'real'.")
        if self.otp_mode.lower() not in {"development", "production"}:
            raise ValueError("OTP_MODE must be 'development' or 'production'.")
        if self.storage_provider.lower() not in {"local", "s3"}:
            raise ValueError("STORAGE_PROVIDER must be 'local' or 's3'.")

        if not self.is_production:
            return self

        problems: list[str] = []

        if self.debug:
            problems.append("DEBUG must be false")
        if self.otp_mode.lower() != "production":
            problems.append("OTP_MODE must be 'production'")
        if self.otp_provider.lower() == "mock":
            problems.append("OTP_PROVIDER must not be 'mock'")
        if self.use_mock_analysis:
            problems.append("ANALYSIS_MODE must be 'real'")

        for name in ("jwt_secret", "token_hash_secret"):
            value = getattr(self, name)
            if value in PLACEHOLDER_SECRETS or len(value) < 32:
                problems.append(f"{name.upper()} must be a random string of at least 32 characters")
        if self.jwt_secret == self.token_hash_secret:
            problems.append("JWT_SECRET and TOKEN_HASH_SECRET must be different")

        if "*" in self.cors_origins_list or not self.cors_origins_list:
            problems.append("CORS_ORIGINS must list exact origins (no '*')")

        for name in ("razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret"):
            if not getattr(self, name):
                problems.append(f"{name.upper()} must be set")

        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
