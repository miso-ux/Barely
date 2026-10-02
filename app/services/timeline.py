"""Order timeline with time differences between steps (BR-23, FR-SV-03)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.i18n import t
from app.models import Order
from app.services import notifications


@dataclass
class Step:
    label: str
    at: datetime
    who: str
    detail: str = ""
    delta: timedelta | None = None  # since the previous step


def format_delta(delta: timedelta | None) -> str:
    if delta is None:
        return ""
    total = int(delta.total_seconds())
    sign = "-" if total < 0 else ""
    total = abs(total)
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{sign}{days} d {hours} h"
    if hours:
        return f"{sign}{hours} h {minutes} min"
    return f"{sign}{minutes} min"


def order_timeline(db: Session, order: Order) -> list[Step]:
    steps: list[Step] = [
        Step(
            t("orders.step.created"),
            order.created_at,
            order.creator.username if order.creator else "",
        )
    ]
    if order.ready_at:
        steps.append(
            Step(
                t("orders.step.ready"),
                order.ready_at,
                order.ready_actor.username if order.ready_actor else "",
            )
        )
    if order.issued_at:
        steps.append(
            Step(
                t("orders.step.issued"),
                order.issued_at,
                order.issue_actor.username if order.issue_actor else "",
            )
        )
    for loan in order.loans:
        if loan.returned_at:
            steps.append(
                Step(
                    t("orders.step.returned"),
                    loan.returned_at,
                    loan.returned_by_user.username
                    if getattr(loan, "returned_by_user", None)
                    else "",
                    f"{loan.barrel.code}: {t('loan.status.' + loan.status.value)}",
                )
            )
    if order.closed_at:
        steps.append(Step(t("orders.step.closed"), order.closed_at, ""))
    if order.cancelled_at:
        steps.append(
            Step(
                t("orders.step.cancelled"),
                order.cancelled_at,
                order.cancel_actor.username if order.cancel_actor else t("audit.system"),
                t(f"order.cancel_reason.{order.cancel_reason}") if order.cancel_reason else "",
            )
        )
    if order.paid_at:
        steps.append(
            Step(t("pumps.payment"), order.paid_at, order.payer.username if order.payer else "")
        )
    for n in notifications.for_link(db, f"/orders/{order.id}"):
        steps.append(Step(t("orders.step.notification"), n.created_at, "", t(n.kind, **n.params)))
        if n.read_at:
            steps.append(
                Step(t("orders.step.notification_read"), n.read_at, "", t(n.kind, **n.params))
            )

    steps.sort(key=lambda s: s.at)
    previous: datetime | None = None
    for step in steps:
        step.delta = step.at - previous if previous is not None else None
        previous = step.at
    return steps
