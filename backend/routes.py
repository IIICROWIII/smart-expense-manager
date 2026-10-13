"""HTTP transport adapter; business rules remain in ExpenseService."""
from fastapi import APIRouter, Query, Request, Response
from .schemas import BudgetInput, CopyBudgetInput, SuggestionInput, Kind, TransactionInput, TransactionPatch

router = APIRouter()


def service(request):
    return request.app.state.service


@router.get("/health")
def health(request: Request):
    return {"status": "ok", "currency": "TRY", "demo": getattr(request.app.state, "demo", False)}


@router.get("/categories")
def categories(request: Request):
    return service(request).categories()


@router.post("/transactions", status_code=201)
def create_transaction(data: TransactionInput, request: Request):
    return service(request).add_transaction(**data.model_dump())


@router.get("/transactions")
def list_transactions(request: Request, month: str | None = None, kind: Kind | None = None, category_id: int | None = Query(None, gt=0), search: str | None = Query(None, max_length=200), unusual: bool = False, limit: int = Query(15, ge=1, le=100), offset: int = Query(0, ge=0)):
    return service(request).list_transactions(month, kind, category_id, search, unusual, limit, offset)


@router.get("/transactions/{identifier}")
def get_transaction(identifier: int, request: Request):
    return service(request).get_transaction(identifier)


@router.patch("/transactions/{identifier}")
def update_transaction(identifier: int, data: TransactionPatch, request: Request):
    return service(request).update_transaction(identifier, **data.model_dump(exclude_unset=True))


@router.delete("/transactions/{identifier}", status_code=204)
def delete_transaction(identifier: int, request: Request):
    service(request).delete_transaction(identifier)
    return Response(status_code=204)


@router.put("/budgets")
def set_budget(data: BudgetInput, request: Request):
    return service(request).set_budget(data.month, data.amount, data.category_id)


@router.get("/budgets")
def get_budgets(month: str, request: Request):
    return service(request).budgets(month)


@router.delete("/budgets/{identifier}", status_code=204)
def delete_budget(identifier: int, request: Request):
    service(request).delete_budget(identifier)
    return Response(status_code=204)


@router.get("/reports/summary")
def summary(month: str, request: Request):
    return service(request).summary(month)


@router.get("/reports/export")
def export(month: str, request: Request):
    content = service(request).export_csv(month)
    return Response(content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="transactions-{month}.csv"'})


@router.get("/alerts")
def alerts(request: Request, month: str | None = None):
    return service(request).alerts(month)


@router.patch("/alerts/{identifier}")
def read_alert(identifier: int, request: Request):
    return service(request).read_alert(identifier)


@router.post("/categories/suggest")
def suggest(data: SuggestionInput, request: Request):
    return service(request).suggest_category(data.description, data.kind)


@router.post("/budgets/copy-previous")
def copy_budgets(data: CopyBudgetInput, request: Request):
    return service(request).copy_budgets(data.month)


@router.get("/reports/history")
def history(month: str, request: Request):
    return service(request).history(month)
