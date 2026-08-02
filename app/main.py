"""All routes. The map for a walkthrough:

  /            serves the frontend page
  /health      liveness check, no auth
  /auth/login  credentials in, token out
  /auth/me     token in, identity out (lets the page adapt to the role)
  /categories  dropdown data, any authenticated user
  /expenses    POST creates (owner = token), GET lists (filter = authorization)
  /expenses/{id}/approve|reject  manager only, never on their own record
  /expenses/{id}/receipt  POST attaches evidence (owner, while pending);
                          GET is the sensitive download: owner or manager,
                          object-checked and audited on every read
  /reports/expenses.csv   monthly export; an employee's query is built
                          filtered to their own rows, a manager's covers the
                          month, and every text cell is neutralized against
                          spreadsheet formula injection

Every route that returns data declares a response_model, so the output
model, not the database row, decides what a client can ever see.
"""

import logging
import sys
import csv
import io
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth import create_token, get_current_user, require_manager, verify_password
from app.config import MAX_RECEIPT_BYTES, TOKEN_TTL_MINUTES, UPLOAD_DIR
from app.database import get_db
from app.models import Category, Expense, ExpenseStatus, Receipt, Role, User, utc_now
from app.schemas import (
    CategoryOut,
    ExpenseCreate,
    ExpenseOut,
    LoginRequest,
    TokenResponse,
    UserOut,
)

# Interactive /docs stays enabled: the app runs locally and the docs page lets a
# reviewer exercise the API directly. A public deployment would disable or gate it.
app = FastAPI(title="Expense Management MVP")

# Security events flow to standard output as JSON lines, where a container
# runtime or log shipper picks them up. Configured once; the audit table in
# the database remains the authoritative record.
_security_log = logging.getLogger("security")
_security_log.setLevel(logging.INFO)
if not _security_log.handlers:
    _security_log.addHandler(logging.StreamHandler(sys.stdout))


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# StaticFiles resolves every request inside this one directory and rejects
# traversal outside it; the page's stylesheet and script load from here.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    # One fixed file served by absolute path: no path parameter, so no
    # directory-traversal surface.
    return FileResponse(FRONTEND_DIR / "index.html")


def _csv_safe(text: str) -> str:
    # Spreadsheet formula injection defense: a cell starting with = + - or @
    # executes as a formula when the file opens in a spreadsheet app. The
    # apostrophe prefix makes it render as plain text instead.
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@app.get("/reports/expenses.csv", response_class=Response)
def monthly_report(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Monthly export. Authorization is the query itself: an employee's report
    is built filtered to their own rows, so nobody else's data can appear in
    the file. A manager's report covers everyone for the month."""
    month_start = date(year, month, 1)
    month_end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

    query = (
        db.query(Expense)
        .filter(Expense.expense_date >= month_start, Expense.expense_date < month_end)
        .order_by(Expense.expense_date, Expense.id)
    )
    if user.role != Role.MANAGER:
        query = query.filter(Expense.user_id == user.id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "owner", "category", "description", "amount_dollars", "status"])
    for e in query.all():
        writer.writerow(
            [
                e.expense_date.isoformat(),
                _csv_safe(e.owner.email),
                _csv_safe(e.category.name),
                _csv_safe(e.description),
                # Integer cents formatted as an exact string; no float math.
                f"{e.amount_cents // 100}.{e.amount_cents % 100:02d}",
                e.status.value,
            ]
        )

    # Exports of expense data are sensitive reads and get audited like one.
    write_audit(db, "report_downloaded", user_id=user.id, detail=f"{year}-{month:02d}")
    db.commit()

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            # Server-generated filename: no user text reaches the header.
            "Content-Disposition": f'attachment; filename="expenses-{year}-{month:02d}.csv"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.middleware("http")
async def revalidate_frontend(request, call_next):
    # The framework sends no Cache-Control on served files, and browsers then
    # cache the app shell heuristically, so users keep a stale page after a
    # deploy. no-cache means store but revalidate: the etag round trip returns
    # 304 while the file is unchanged and fresh content the request after it
    # changes. Found live, when a rebuilt container kept serving yesterday's
    # page to an already-open browser.
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email).first()

    # One generic error for both unknown email and wrong password: a split
    # response would let an attacker enumerate which emails have accounts.
    if user is None or not verify_password(body.password, user.password_hash):
        write_audit(db, "login_failed", user_id=user.id if user else None)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    write_audit(db, "login_ok", user_id=user.id)
    db.commit()
    return TokenResponse(
        access_token=create_token(user),
        expires_in=TOKEN_TTL_MINUTES * 60,
    )


@app.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    """Who does the server think I am? Lets the frontend adapt to the role."""
    return user


@app.get("/categories", response_model=list[CategoryOut])
def list_categories(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Category]:
    return db.query(Category).order_by(Category.name).all()


@app.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(
    body: ExpenseCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Expense:
    if db.get(Category, body.category_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown category")

    # Identity comes from the token, never the request body: a client cannot
    # file an expense as someone else.
    expense = Expense(user_id=user.id, **body.model_dump())
    db.add(expense)
    # Flush assigns the id inside the open transaction; the expense and its
    # audit row then commit together or not at all.
    db.flush()
    write_audit(db, "expense_created", user_id=user.id, target_id=expense.id)
    db.commit()
    return expense


@app.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> list[Expense]:
    query = db.query(Expense)
    if user.role == Role.MANAGER:
        # The manager view is the review queue: everyone's pending expenses.
        query = query.filter(Expense.status == ExpenseStatus.PENDING)
    else:
        # Object-level authorization for lists is the filter itself:
        # an employee's query can only ever return their own rows.
        query = query.filter(Expense.user_id == user.id)
    return (
        query.order_by(Expense.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )


def _decide_expense(
    expense_id: int, decision: ExpenseStatus, manager: User, db: Session
) -> Expense:
    """Shared by approve and reject. Three checks in order: the record
    exists (404), it is not the decider's own (403, separation of duties),
    and it is still pending (409, decisions are final). Only then does the
    status change, and the change is audited with who did it."""
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Separation of duties: approval authority never applies to your own record.
    if expense.user_id == manager.id:
        write_audit(
            db, "self_decision_denied", user_id=manager.id, target_id=expense.id
        )
        # Denials commit their own audit row: there is no state change to
        # join, and a raise without a commit would roll the trail back.
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot decide your own expense",
        )

    if expense.status != ExpenseStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Expense is already decided"
        )

    expense.status = decision
    # The record carries its own attribution; the audit row is the second copy.
    expense.decided_by = manager.id
    expense.decided_at = utc_now()
    write_audit(
        db,
        "expense_approved" if decision == ExpenseStatus.APPROVED else "expense_rejected",
        user_id=manager.id,
        target_id=expense.id,
    )
    # One commit: the decision, its attribution, and its audit row are atomic.
    db.commit()
    return expense


@app.post("/expenses/{expense_id}/approve", response_model=ExpenseOut)
def approve_expense(
    expense_id: int,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> Expense:
    return _decide_expense(expense_id, ExpenseStatus.APPROVED, manager, db)


@app.post("/expenses/{expense_id}/reject", response_model=ExpenseOut)
def reject_expense(
    expense_id: int,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> Expense:
    return _decide_expense(expense_id, ExpenseStatus.REJECTED, manager, db)


# Allowed receipt types: declared type maps to the magic bytes the file must
# open with and the extension the server stores. The declared Content-Type is
# client input; the file's own first bytes are the check against it.
RECEIPT_TYPES = {
    "image/png": (b"\x89PNG", ".png"),
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "application/pdf": (b"%PDF", ".pdf"),
}


@app.post(
    "/expenses/{expense_id}/receipt",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_receipt(
    expense_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Expense:
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Only the owner attaches evidence to an expense, whatever the role.
    if expense.user_id != user.id:
        write_audit(db, "access_denied", user_id=user.id, target_id=expense.id,
                    detail="receipt upload, not owner")
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your expense")

    # Evidence arrives before the decision; a decided expense is immutable.
    if expense.status != ExpenseStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Expense is already decided")
    if expense.receipt is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Receipt already attached")

    spec = RECEIPT_TYPES.get(file.content_type or "")
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Receipts are PNG, JPEG, or PDF",
        )
    magic, extension = spec

    # Read at most one byte past the cap: enough to know it is too large
    # without ever buffering an unbounded body.
    data = await file.read(MAX_RECEIPT_BYTES + 1)
    if len(data) > MAX_RECEIPT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Receipt exceeds the size limit",
        )
    if not data.startswith(magic):
        # Declared type and actual bytes disagree; trust neither.
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content does not match its declared type",
        )

    # Server-generated name: the client's filename never becomes a path.
    stored_name = uuid4().hex + extension
    upload_dir = Path(UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / stored_name).write_bytes(data)

    db.add(
        Receipt(
            expense_id=expense.id,
            stored_name=stored_name,
            original_name=(file.filename or "receipt")[:255],
            content_type=file.content_type,
            size_bytes=len(data),
        )
    )
    write_audit(db, "receipt_uploaded", user_id=user.id, target_id=expense.id)
    db.commit()
    db.refresh(expense)
    return expense


@app.get("/expenses/{expense_id}/receipt")
def download_receipt(
    expense_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """The sensitive download. The check is object-level (owner or manager),
    every successful read is audited, and the served filename is
    server-generated so no user text reaches a response header."""
    expense = db.get(Expense, expense_id)
    if expense is None or expense.receipt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if expense.user_id != user.id and user.role != Role.MANAGER:
        write_audit(db, "access_denied", user_id=user.id, target_id=expense.id,
                    detail="receipt download, not owner or manager")
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your expense")

    path = Path(UPLOAD_DIR) / expense.receipt.stored_name
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Reads of evidence are audited like writes: who saw it, when.
    write_audit(db, "receipt_downloaded", user_id=user.id, target_id=expense.id)
    db.commit()

    extension = path.suffix
    return FileResponse(
        path,
        media_type=expense.receipt.content_type,
        filename=f"receipt-{expense.id}{extension}",
        # nosniff: the browser must honor the declared type, not guess one.
        headers={"X-Content-Type-Options": "nosniff"},
    )
