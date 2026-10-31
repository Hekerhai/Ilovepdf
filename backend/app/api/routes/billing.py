from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import container, user
from app.container import Container
from app.infra.db import as_utc
from app.services.actors import Actor

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutIn(BaseModel):
    plan: Literal["pro", "business"]
    interval: Literal["month", "year"] = "month"
    provider: Literal["stripe", "razorpay"] = "stripe"
    seats: int = Field(1, ge=1, le=1000)
    team_id: str | None = None


@router.get("/plans")
def plans(c: Container = Depends(container)) -> dict:
    return c.billing.catalog()


@router.post("/checkout")
def checkout(body: CheckoutIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    session = c.billing.checkout(
        a.user, plan_id=body.plan, interval=body.interval, provider=body.provider,
        seats=body.seats, team_id=body.team_id,
    )  # fmt: skip
    return {"provider": session.provider, "url": session.url, "client_payload": session.client_payload}


class PassIn(BaseModel):
    provider: Literal["stripe", "razorpay"] = "stripe"


@router.post("/pass", summary="Buy a 7-day pass: one payment, no renewal")
def buy_pass(body: PassIn, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    session = c.billing.buy_pass(a.user, provider=body.provider)
    return {"provider": session.provider, "url": session.url, "client_payload": session.client_payload}


@router.get("/subscriptions")
def subscriptions(a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    return {
        "subscriptions": [
            {
                "id": s.id,
                "plan": s.plan_id,
                "provider": s.provider,
                "status": s.status,
                "seats": s.seats,
                "owner_type": s.owner_type,
                "owner_id": s.owner_id,
                "current_period_end": as_utc(s.current_period_end).isoformat() if s.current_period_end else None,
            }
            for s in c.billing.subscriptions(a.user)
        ]
    }


@router.post("/subscriptions/{subscription_id}/cancel", status_code=202)
def cancel(subscription_id: str, a: Actor = Depends(user), c: Container = Depends(container)) -> dict:
    c.billing.cancel(a.user, subscription_id)
    return {"cancelling": True}


@router.post("/webhooks/{provider}", include_in_schema=False)
async def webhook(provider: str, request: Request, c: Container = Depends(container)) -> dict:
    payload = await request.body()
    event = c.billing.handle_webhook(provider, payload, dict(request.headers))
    return {"received": True, "kind": event.kind}
