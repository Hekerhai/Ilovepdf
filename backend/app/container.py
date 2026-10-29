"""Composition root: the only place that knows which concrete adapters implement each port."""

from dataclasses import dataclass
from functools import lru_cache

from app.config import Settings, get_settings
from app.domain.ports import AIProvider, DocumentConverter, FileStorage, JobQueue, Mailer
from app.engines.converters import GotenbergConverter, LibreOfficeConverter
from app.engines.ghostscript import Ghostscript
from app.infra.ai.providers import AnthropicProvider, NoAIProvider, OpenAICompatibleProvider
from app.infra.db import Database
from app.infra.mailer import ConsoleMailer, SmtpMailer
from app.infra.payments.razorpay_gateway import RazorpayGateway
from app.infra.payments.stripe_gateway import StripeGateway
from app.infra.queue import InlineJobQueue, RQJobQueue
from app.infra.ratelimit import MemoryRateLimiter, RedisRateLimiter
from app.infra.storage import LocalStorage, S3Storage
from app.services.auth import AuthService
from app.services.billing import BillingService
from app.services.jobs import JobService
from app.services.privacy import PrivacyService
from app.services.quota import QuotaService
from app.services.teams import TeamService
from app.services.workflows import WorkflowService
from app.tools.registry import ToolRegistry, default_registry


@dataclass
class Container:
    settings: Settings
    db: Database
    storage: FileStorage
    queue: JobQueue
    mailer: Mailer
    registry: ToolRegistry
    ai: AIProvider
    converter: DocumentConverter
    quota: QuotaService
    jobs: JobService
    auth: AuthService
    teams: TeamService
    workflows: WorkflowService
    billing: BillingService
    privacy: PrivacyService
    limiter: MemoryRateLimiter | RedisRateLimiter


def build_storage(s: Settings) -> FileStorage:
    if s.storage_backend == "s3":
        return S3Storage(
            bucket=s.s3_bucket,
            endpoint_url=s.s3_endpoint_url,
            access_key=s.s3_access_key,
            secret_key=s.s3_secret_key,
            region=s.s3_region,
        )
    return LocalStorage(s.storage_dir)


def build_ai(s: Settings) -> AIProvider:
    if s.ai_provider == "anthropic" and s.ai_api_key:
        return AnthropicProvider(s.ai_api_key, s.ai_model)
    if s.ai_provider == "openai" and (s.ai_api_key or s.ai_base_url):
        return OpenAICompatibleProvider(s.ai_api_key, s.ai_model, s.ai_base_url or "https://api.openai.com/v1")
    return NoAIProvider()


def build_container(settings: Settings | None = None) -> Container:
    s = settings or get_settings()
    db = Database(s.database_url)
    db.migrate()
    storage = build_storage(s)
    queue: JobQueue = InlineJobQueue() if s.queue_mode == "inline" else RQJobQueue(s.redis_url)
    mailer: Mailer = (
        SmtpMailer(s.smtp_host, s.smtp_port, s.mail_from, s.smtp_user, s.smtp_password)
        if s.smtp_host
        else ConsoleMailer()
    )
    registry = default_registry()
    ai = build_ai(s)
    converter: DocumentConverter = (
        GotenbergConverter(s.gotenberg_url, s.tool_timeout_seconds)
        if s.gotenberg_url
        else LibreOfficeConverter(s.soffice_bin, s.tool_timeout_seconds)
    )
    quota = QuotaService()
    jobs = JobService(
        db=db,
        storage=storage,
        queue=queue,
        registry=registry,
        quota=quota,
        work_root=s.work_dir,
        file_ttl_hours=s.file_ttl_hours,
        converter=converter,
        ai=ai,
        ghostscript=Ghostscript(s.ghostscript_bin, s.tool_timeout_seconds),
        ocr_languages=s.ocr_languages,
        tool_timeout=s.tool_timeout_seconds,
    )
    if isinstance(queue, InlineJobQueue):
        queue.runner = jobs.run
    auth = AuthService(
        db=db,
        mailer=mailer,
        secret_key=s.secret_key,
        public_url=s.public_url,
        brand_name=s.brand_name,
        token_minutes=s.access_token_minutes,
        magic_link_minutes=s.magic_link_minutes,
        google_client_id=s.google_client_id,
        google_client_secret=s.google_client_secret,
    )
    billing = BillingService(
        db=db,
        gateways={
            "stripe": StripeGateway(s.stripe_secret_key, s.stripe_webhook_secret),
            "razorpay": RazorpayGateway(s.razorpay_key_id, s.razorpay_key_secret, s.razorpay_webhook_secret),
        },
        public_url=s.public_url,
    )
    return Container(
        settings=s,
        db=db,
        storage=storage,
        queue=queue,
        mailer=mailer,
        registry=registry,
        ai=ai,
        converter=converter,
        quota=quota,
        jobs=jobs,
        auth=auth,
        teams=TeamService(db=db, mailer=mailer, public_url=s.public_url, brand_name=s.brand_name),
        workflows=WorkflowService(db=db, jobs=jobs),
        billing=billing,
        privacy=PrivacyService(db=db, storage=storage, billing=billing),
        limiter=MemoryRateLimiter() if s.queue_mode == "inline" else RedisRateLimiter(s.redis_url),
    )


@lru_cache
def get_container() -> Container:
    return build_container()
