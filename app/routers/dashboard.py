from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import require_user
from app.auth.permissions import Perm
from app.db import get_db
from app.models import LoanStatus, OrderStatus, User
from app.services import debtors as debtors_service
from app.services import orders as orders_service
from app.services import penalties as penalties_service
from app.services import pumps as pumps_service
from app.services import stock
from app.web import render

router = APIRouter()


@router.get("/")
def dashboard(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    context: dict = {}
    if user.has_permission(Perm.STOCK_READ_FREE):
        context["free"] = stock.free_count(db)
        context["free_pumps"] = pumps_service.total_free(db)
    if user.has_permission(Perm.ORDERS_READ_OWN):
        own = orders_service.list_orders(db, user_id=user.id)
        context["open_orders"] = [
            o for o in own if o.status in (OrderStatus.PENDING, OrderStatus.READY)
        ]
        context["active_loans"] = [
            loan
            for o in own
            if o.status is OrderStatus.ISSUED
            for loan in o.loans
            if loan.status in (LoanStatus.ON_LOAN, LoanStatus.OVERDUE)
        ]
        context["unpaid_total"] = penalties_service.unpaid_total(db, user.id)
        context["is_debtor"] = debtors_service.is_debtor(db, user)
    return render(request, "dashboard.html", context)
