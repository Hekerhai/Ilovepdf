"""Plan catalogue and entitlements.

Plans are data, not code: add or tune a plan here without touching the services that enforce it.
Prices are in the smallest currency unit (cents / paise).
"""

from dataclasses import dataclass, field
from enum import StrEnum

MB = 1024 * 1024


class PlanId(StrEnum):
    GUEST = "guest"
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"


class BillingInterval(StrEnum):
    MONTH = "month"
    YEAR = "year"


@dataclass(frozen=True)
class Price:
    usd: int
    inr: int


@dataclass(frozen=True)
class Plan:
    id: PlanId
    name: str
    max_file_bytes: int
    max_files_per_task: int
    tasks_per_day: int | None  # None = unlimited (fair use)
    premium_tools: bool
    max_workflows: int | None
    team_workspace: bool = False
    monthly_api_credits: int = 250
    esign_requests_per_month: int | None = 3  # None = unlimited
    prices: dict[BillingInterval, Price] = field(default_factory=dict)
    per_seat: bool = False
    min_seats: int = 1
    highlights: tuple[str, ...] = ()

    @property
    def purchasable(self) -> bool:
        return bool(self.prices)


PLANS: dict[PlanId, Plan] = {
    PlanId.GUEST: Plan(
        id=PlanId.GUEST,
        name="Guest",
        max_file_bytes=25 * MB,
        max_files_per_task=5,
        tasks_per_day=10,
        premium_tools=False,
        max_workflows=0,
        monthly_api_credits=0,
        esign_requests_per_month=0,
    ),
    PlanId.FREE: Plan(
        id=PlanId.FREE,
        name="Free",
        max_file_bytes=50 * MB,
        max_files_per_task=10,
        tasks_per_day=25,
        premium_tools=False,
        max_workflows=0,
        highlights=(
            "All in-browser tools, unlimited",
            "25 server tasks a day",
            "Files up to 50 MB",
            "3 signature requests a month",
        ),
    ),
    PlanId.PRO: Plan(
        id=PlanId.PRO,
        name="Pro",
        max_file_bytes=1024 * MB,
        max_files_per_task=200,
        tasks_per_day=None,
        premium_tools=True,
        max_workflows=20,
        monthly_api_credits=1000,
        esign_requests_per_month=None,
        prices={
            BillingInterval.MONTH: Price(usd=600, inr=39900),
            BillingInterval.YEAR: Price(usd=4800, inr=319900),
        },
        highlights=(
            "Every tool, including OCR, PDF to Office and AI",
            "Unlimited tasks, files up to 1 GB",
            "Batch workflows",
            "Unlimited signature requests",
            "1,000 API credits a month",
        ),
    ),
    PlanId.BUSINESS: Plan(
        id=PlanId.BUSINESS,
        name="Business",
        max_file_bytes=2048 * MB,
        max_files_per_task=500,
        tasks_per_day=None,
        premium_tools=True,
        max_workflows=None,
        team_workspace=True,
        monthly_api_credits=5000,
        esign_requests_per_month=None,
        per_seat=True,
        min_seats=3,
        prices={
            BillingInterval.MONTH: Price(usd=500, inr=34900),
            BillingInterval.YEAR: Price(usd=4800, inr=334900),
        },
        highlights=(
            "Everything in Pro",
            "Team workspace with roles and shared workflows",
            "Files up to 2 GB",
            "5,000 API credits a month",
        ),
    ),
}


# A one-time payment that gives Pro for a week, for people who need it once. Never renews.
PASS_PLAN = PlanId.PRO
PASS_DAYS = 7
PASS_PRICE = Price(usd=300, inr=19900)


def get_plan(plan_id: str | PlanId) -> Plan:
    return PLANS[PlanId(plan_id)]
