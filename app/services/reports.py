"""Reports and CSV export (FR-RE-01..05, FR-SV-04..07, FR-PU-06 lives in pumps).

Every report is a `Table`: translated column keys plus plain rows, so the same data renders
as HTML or as CSV. Access by holders of reports.read_all is written to the audit log by the
router (FR-SV-08).
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import Perm
from app.i18n import t
from app.models import (
    Barrel,
    BarrelStatus,
    BarrelStatusHistory,
    Invoice,
    InvoiceKind,
    InvoiceStatus,
    Loan,
    Order,
    OrderKind,
    OrderStatus,
    User,
)
from app.services import dates, debtors
from app.web import format_datetime

ZERO = Decimal("0.00")


@dataclass
class Table:
    key: str
    columns: list[tuple[str, str]]  # (field, i18n label key)
    rows: list[dict[str, Any]]
    totals: dict[str, Any] = field(default_factory=dict)
    date_from: date | None = None
    date_to: date | None = None

    def csv(self) -> str:
        """Semicolon-separated UTF-8 with BOM: opens correctly in Excel with Slovak locale."""
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow([t(label) for _, label in self.columns])
        for row in self.rows:
            writer.writerow([_cell(row.get(field_name)) for field_name, _ in self.columns])
        if self.totals:
            writer.writerow(
                [_cell(self.totals.get(field_name, "")) for field_name, _ in self.columns]
            )
        return "﻿" + buffer.getvalue()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return format_datetime(value)
    if isinstance(value, date):
        return dates.format_date(value)
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


# Which permissions open which report. The first key is the operational one.
REPORT_PERMISSIONS: Final[dict[str, tuple[str, ...]]] = {
    "movements": (Perm.REPORTS_READ_OPERATIONS, Perm.REPORTS_READ_ALL),
    "environmental": (Perm.REPORTS_READ_OPERATIONS, Perm.REPORTS_READ_ALL),
    "stock": (Perm.REPORTS_READ_OPERATIONS, Perm.REPORTS_READ_ALL),
    "debtors": (Perm.DEBTORS_READ, Perm.REPORTS_READ_ALL),
    "invoices": (Perm.REPORTS_READ_INVOICING, Perm.REPORTS_READ_ALL),
    "roles": (Perm.REPORTS_READ_ALL,),
}


@dataclass(frozen=True)
class Filters:
    date_from: date
    date_to: date
    user: str = ""  # customer username (contains)
    actor: str = ""  # staff username (contains)
    barrel: str = ""  # barrel code (contains)
    status: str = ""  # target status / status filter
    reason: str = ""  # history reason


def _in_period(moment: datetime, filters: Filters) -> bool:
    local = dates.local_date(moment)
    return filters.date_from <= local <= filters.date_to


def _matches(haystack: str | None, needle: str) -> bool:
    return not needle or (haystack or "").lower().find(needle.lower()) >= 0


def movements(db: Session, filters: Filters) -> Table:
    """FR-RE-01 / FR-SV-04: every barrel status change in the period with free filters."""
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    loans_by_id: dict[int, Loan] = {}
    history = db.scalars(
        select(BarrelStatusHistory).order_by(BarrelStatusHistory.created_at, BarrelStatusHistory.id)
    ).all()
    loan_ids = {h.loan_id for h in history if h.loan_id}
    if loan_ids:
        loans_by_id = {
            loan.id: loan for loan in db.scalars(select(Loan).where(Loan.id.in_(loan_ids)))
        }
    for h in history:
        if not _in_period(h.created_at, filters):
            continue
        loan = loans_by_id.get(h.loan_id) if h.loan_id else None
        customer = loan.user.username if loan else ""
        actor = h.actor.username if h.actor else ""
        if not (
            _matches(h.barrel.code, filters.barrel)
            and _matches(customer, filters.user)
            and _matches(actor, filters.actor)
            and (not filters.status or h.to_status.value == filters.status)
            and (not filters.reason or h.reason == filters.reason)
        ):
            continue
        counts[h.reason] = counts.get(h.reason, 0) + 1
        rows.append(
            {
                "when": h.created_at,
                "barrel": h.barrel.code,
                "from_status": t(f"barrel.status.{h.from_status.value}") if h.from_status else "",
                "to_status": t(f"barrel.status.{h.to_status.value}"),
                "reason": t(f"barrel.reason.{h.reason}"),
                "customer": customer,
                "actor": actor,
                "note": h.note or "",
            }
        )
    summary = ", ".join(
        f"{t('barrel.reason.' + reason)}: {n}" for reason, n in sorted(counts.items())
    )
    return Table(
        "movements",
        [
            ("when", "audit.when"),
            ("barrel", "barrels.code"),
            ("from_status", "barrels.from"),
            ("to_status", "barrels.to"),
            ("reason", "barrels.reason"),
            ("customer", "orders.user"),
            ("actor", "report.actor"),
            ("note", "barrels.note"),
        ],
        rows,
        totals={"when": t("report.total"), "barrel": len(rows), "reason": summary},
        date_from=filters.date_from,
        date_to=filters.date_to,
    )


ENVIRONMENTAL_STATUSES = (BarrelStatus.RETIRED, BarrelStatus.WRITTEN_OFF, BarrelStatus.LOST)


def environmental(db: Session, filters: Filters) -> Table:
    """FR-RE-02: barrels retired, written off or lost in the period."""
    rows = []
    history = db.scalars(
        select(BarrelStatusHistory)
        .where(BarrelStatusHistory.to_status.in_(ENVIRONMENTAL_STATUSES))
        .order_by(BarrelStatusHistory.created_at)
    )
    for h in history:
        if not _in_period(h.created_at, filters):
            continue
        rows.append(
            {
                "when": h.created_at,
                "barrel": h.barrel.code,
                "status": t(f"barrel.status.{h.to_status.value}"),
                "reason": t(f"barrel.reason.{h.reason}"),
                "loan_count": h.barrel.loan_count,
                "added_at": dates.local_date(h.barrel.added_at),
                "note": h.note or "",
                "actor": h.actor.username if h.actor else "",
            }
        )
    return Table(
        "environmental",
        [
            ("when", "audit.when"),
            ("barrel", "barrels.code"),
            ("status", "barrels.status"),
            ("reason", "barrels.reason"),
            ("loan_count", "barrels.loan_count"),
            ("added_at", "barrels.added_at"),
            ("note", "barrels.note"),
            ("actor", "report.actor"),
        ],
        rows,
        totals={"when": t("report.total"), "barrel": len(rows)},
        date_from=filters.date_from,
        date_to=filters.date_to,
    )


def stock(db: Session, filters: Filters) -> Table:
    """FR-SV-05: every barrel with age and loan count."""
    today = dates.today_local()
    rows = []
    for barrel in db.scalars(select(Barrel).order_by(Barrel.code)):
        if filters.status and barrel.status.value != filters.status:
            continue
        if not _matches(barrel.code, filters.barrel):
            continue
        rows.append(
            {
                "barrel": barrel.code,
                "status": t(f"barrel.status.{barrel.status.value}"),
                "loan_count": barrel.loan_count,
                "added_at": dates.local_date(barrel.added_at),
                "age_days": (today - dates.local_date(barrel.added_at)).days,
                "changes": len(barrel.history),
            }
        )
    return Table(
        "stock",
        [
            ("barrel", "barrels.code"),
            ("status", "barrels.status"),
            ("loan_count", "barrels.loan_count"),
            ("added_at", "barrels.added_at"),
            ("age_days", "report.age_days"),
            ("changes", "report.changes"),
        ],
        rows,
        totals={"barrel": len(rows)},
    )


def debtors_table(db: Session, filters: Filters) -> Table:
    """FR-RE-03."""
    rows = [
        {
            "user": row.user.username,
            "name": row.user.display_name,
            "overdue_loans": row.overdue_loans,
            "unpaid_amount": row.unpaid_amount,
            "days_overdue": row.days_overdue,
        }
        for row in debtors.list_debtors(db)
        if _matches(row.user.username, filters.user)
    ]
    return Table(
        "debtors",
        [
            ("user", "orders.user"),
            ("name", "users.display_name"),
            ("overdue_loans", "debtors.overdue_loans"),
            ("unpaid_amount", "debtors.unpaid_amount"),
            ("days_overdue", "debtors.days_overdue"),
        ],
        rows,
        totals={
            "user": t("report.total"),
            "overdue_loans": sum(r["overdue_loans"] for r in rows),
            "unpaid_amount": sum((r["unpaid_amount"] for r in rows), ZERO),
        },
    )


def invoices_table(db: Session, filters: Filters) -> Table:
    """FR-RE-05 / FR-SV-06: count and value per status for invoices created in the period."""
    per_status: dict[InvoiceStatus, list[Invoice]] = {s: [] for s in InvoiceStatus}
    for invoice in db.scalars(select(Invoice).where(Invoice.kind == InvoiceKind.INVOICE)):
        if _in_period(invoice.created_at, filters) and _matches(
            invoice.customer.username, filters.user
        ):
            per_status[invoice.status].append(invoice)
    rows = [
        {
            "status": t(f"invoice.status.{status.value}"),
            "count": len(items),
            "total": sum((i.total for i in items), ZERO),
            "paid": sum((i.total for i in items if i.paid_at), ZERO),
        }
        for status, items in per_status.items()
    ]
    return Table(
        "invoices",
        [
            ("status", "invoice.status"),
            ("count", "orders.count"),
            ("total", "pumps.total"),
            ("paid", "report.paid"),
        ],
        rows,
        totals={
            "status": t("report.total"),
            "count": sum(r["count"] for r in rows),
            "total": sum((r["total"] for r in rows), ZERO),
            "paid": sum((r["paid"] for r in rows), ZERO),
        },
        date_from=filters.date_from,
        date_to=filters.date_to,
    )


def _hours(delta: timedelta) -> Decimal:
    return Decimal(delta.total_seconds() / 3600).quantize(Decimal("0.1"))


def roles_work(db: Session, filters: Filters) -> Table:
    """FR-SV-07: how each staff member worked in the period."""
    stats: dict[int, dict[str, Any]] = {}
    users = {u.id: u for u in db.scalars(select(User))}

    def row(user_id: int | None) -> dict[str, Any] | None:
        if user_id is None or user_id not in users:
            return None
        if user_id not in stats:
            stats[user_id] = {
                "actor": users[user_id].username,
                "prepared": 0,
                "issued": 0,
                "issue_hours": [],
                "returns": 0,
                "invoices_issued": 0,
                "invoice_hours": [],
            }
        return stats[user_id]

    for order in db.scalars(select(Order).where(Order.kind == OrderKind.BARREL)):
        if order.ready_at and _in_period(order.ready_at, filters):
            if (r := row(order.ready_by)) is not None:
                r["prepared"] += 1
        if order.issued_at and _in_period(order.issued_at, filters):
            if (r := row(order.issued_by)) is not None:
                r["issued"] += 1
                r["issue_hours"].append(_hours(order.issued_at - order.created_at))
        for loan in order.loans:
            if loan.returned_at and _in_period(loan.returned_at, filters):
                if (r := row(loan.returned_by)) is not None:
                    r["returns"] += 1
    for invoice in db.scalars(select(Invoice).where(Invoice.kind == InvoiceKind.INVOICE)):
        if invoice.issued_at and _in_period(invoice.issued_at, filters):
            if (r := row(invoice.issued_by)) is not None:
                r["invoices_issued"] += 1
                r["invoice_hours"].append(_hours(invoice.issued_at - invoice.created_at))

    rows = []
    for data in sorted(stats.values(), key=lambda d: d["actor"]):
        if not _matches(data["actor"], filters.actor):
            continue
        issue_hours = data["issue_hours"]
        invoice_hours = data["invoice_hours"]
        rows.append(
            {
                "actor": data["actor"],
                "prepared": data["prepared"],
                "issued": data["issued"],
                "avg_issue_hours": (sum(issue_hours) / len(issue_hours)).quantize(Decimal("0.1"))
                if issue_hours
                else "",
                "returns": data["returns"],
                "invoices_issued": data["invoices_issued"],
                "avg_invoice_hours": (sum(invoice_hours) / len(invoice_hours)).quantize(
                    Decimal("0.1")
                )
                if invoice_hours
                else "",
            }
        )
    return Table(
        "roles",
        [
            ("actor", "report.actor"),
            ("prepared", "report.prepared"),
            ("issued", "report.issued"),
            ("avg_issue_hours", "report.avg_issue_hours"),
            ("returns", "report.returns"),
            ("invoices_issued", "report.invoices_issued"),
            ("avg_invoice_hours", "report.avg_invoice_hours"),
        ],
        rows,
        date_from=filters.date_from,
        date_to=filters.date_to,
    )


BUILDERS: Final = {
    "movements": movements,
    "environmental": environmental,
    "stock": stock,
    "debtors": debtors_table,
    "invoices": invoices_table,
    "roles": roles_work,
}


def build(db: Session, key: str, filters: Filters) -> Table:
    return BUILDERS[key](db, filters)


def available_for(user: User) -> list[str]:
    return [key for key, perms in REPORT_PERMISSIONS.items() if user.has_any_permission(*perms)]


def order_statuses_for_filter() -> list[str]:
    return [s.value for s in OrderStatus]
