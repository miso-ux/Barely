from fastapi import APIRouter, Depends, Request

from app.auth.deps import require_user
from app.models import User
from app.web import render

router = APIRouter()


@router.get("/")
def dashboard(request: Request, user: User = Depends(require_user)):
    return render(request, "dashboard.html")
