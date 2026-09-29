from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.deps import get_db, require
from app.modules.reports import service

router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateRequest(BaseModel):
    type: str
    format: str = "csv"


@router.get("/catalog")
def catalog(ctx=Depends(require("reports", "read"))):
    return {"data": {"types": service.REPORT_TYPES, "formats": service.FORMATS}}


@router.post("/generate")
def generate(
    body: GenerateRequest, ctx=Depends(require("reports", "create")),
    db: Session = Depends(get_db, scope="function"),
):
    result = service.generate(db, ctx, body.type, body.format)
    record_audit(
        db, tenant_id=ctx.user.tenant_id, action="report.generate",
        actor_id=ctx.user.id, actor_email=ctx.user.email,
        detail={"type": body.type, "format": body.format, "rows": result["row_count"]},
    )
    return Response(
        content=result["content"],
        media_type=result["media_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            "X-Row-Count": str(result["row_count"]),
        },
    )
