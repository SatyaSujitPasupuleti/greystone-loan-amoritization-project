"""FastAPI application for managing users and loans with amortization utilities.

This module exposes endpoints to create and read users and loans, compute loan
schedules, and summarize loan balances. Financial math uses Decimal with
cent-level rounding for accuracy.
"""
from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from decimal import Decimal, ROUND_HALF_UP, getcontext
import logging

from . import models, schemas
from .database import engine, get_db

# Configure module logger.
logger = logging.getLogger("loan_amori")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Create tables on startup (simple dev setup).
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Loan Amori API")

# Use high precision for intermediate Decimal math.
getcontext().prec = 28


def _to_cents(value: Decimal) -> Decimal:
    """Return value rounded to cents using ROUND_HALF_UP."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _compute_monthly_payment(principal: Decimal, monthly_rate: Decimal, term_months: int) -> Decimal:
    """Compute the fixed monthly payment for an amortizing loan.

    If r = monthly_rate and n = term_months, principal P:
    - If r == 0: M = P / n
    - Else:     M = P * [ r (1+r)^n / ((1+r)^n - 1) ]
    """
    if monthly_rate == 0:
        return _to_cents(principal / Decimal(term_months))
    one_plus_r_pow_n = (Decimal("1") + monthly_rate) ** term_months
    raw_payment = principal * (monthly_rate * one_plus_r_pow_n) / (one_plus_r_pow_n - Decimal("1"))
    return _to_cents(raw_payment)


def _amortization_state_at_month(
    principal: Decimal, monthly_rate: Decimal, term_months: int, month: int
) -> tuple[Decimal, Decimal, Decimal]:
    """Return remaining, total principal paid, and total interest paid after `month` payments.

    Per-period interest equals remaining * r, rounded to cents. Principal paid
    equals payment minus interest. On the final month, principal is forced to
    clear the remaining balance and interest is adjusted so payment equals
    principal plus interest.
    """
    monthly_payment = _compute_monthly_payment(principal, monthly_rate, term_months)

    remaining = principal
    total_interest_paid = Decimal("0")
    total_principal_paid = Decimal("0")

    if month <= 0:
        return remaining, total_principal_paid, total_interest_paid

    for i in range(1, month + 1):
        if monthly_rate == 0:
            interest = Decimal("0")
        else:
            interest = _to_cents(remaining * monthly_rate)

        principal_payment = monthly_payment - interest

        if i == term_months:
            principal_payment = remaining
            interest = monthly_payment - principal_payment

        if principal_payment > remaining:
            principal_payment = remaining

        remaining = remaining - principal_payment
        total_interest_paid += interest
        total_principal_paid += principal_payment

    return remaining, total_principal_paid, total_interest_paid


def current_principal_balance_at_month(
    principal: Decimal, monthly_rate: Decimal, term_months: int, month: int
) -> Decimal:
    """Return the remaining principal after `month` payments, rounded to cents."""
    remaining, _, _ = _amortization_state_at_month(principal, monthly_rate, term_months, month)
    return _to_cents(remaining)


def total_principal_paid_at_month(
    principal: Decimal, monthly_rate: Decimal, term_months: int, month: int
) -> Decimal:
    """Return the aggregate principal paid by the end of `month`, rounded to cents."""
    _, total_principal_paid, _ = _amortization_state_at_month(principal, monthly_rate, term_months, month)
    return _to_cents(total_principal_paid)


def total_interest_paid_at_month(
    principal: Decimal, monthly_rate: Decimal, term_months: int, month: int
) -> Decimal:
    """Return the aggregate interest paid by the end of `month`, rounded to cents."""
    _, _, total_interest_paid = _amortization_state_at_month(principal, monthly_rate, term_months, month)
    return _to_cents(total_interest_paid)


# User endpoints
@app.post("/users", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Create a new user with a unique username and email."""
    logger.info("POST /users - creating user username=%s email=%s", user.username, user.email)
    existing = (
        db.query(models.User)
        .filter((models.User.username == user.username) | (models.User.email == user.email))
        .first()
    )
    if existing:
        logger.info("POST /users - conflict for username=%s or email=%s", user.username, user.email)
        raise HTTPException(status_code=400, detail="Username or email already exists")

    db_user = models.User(**user.model_dump())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    logger.info("POST /users - created user id=%s", db_user.id)
    return db_user


@app.get("/users", response_model=List[schemas.UserRead])
def list_users(db: Session = Depends(get_db)):
    """Return all users."""
    users = db.query(models.User).all()
    logger.info("GET /users - returned count=%s", len(users))
    return users


@app.get("/users/{user_id}/loans", response_model=List[schemas.LoanRead])
def list_loans_for_user(user_id: int, db: Session = Depends(get_db)):
    """Return all loans owned by a specific user."""
    logger.info("GET /users/%s/loans - listing", user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        logger.info("GET /users/%s/loans - user not found", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    loans = db.query(models.Loan).filter(models.Loan.user_id == user_id).all()
    logger.info("GET /users/%s/loans - returned count=%s", user_id, len(loans))
    return loans


# Loan endpoints
@app.post("/loans", response_model=schemas.LoanRead, status_code=status.HTTP_201_CREATED)
def create_loan(loan: schemas.LoanCreate, db: Session = Depends(get_db)):
    """Create a new loan for the specified owner."""
    logger.info(
        "POST /loans - creating loan user_id=%s amount=%s rate=%s term=%s",
        loan.user_id,
        loan.amount,
        loan.annual_interest_rate,
        loan.loan_term_in_months,
    )
    user = db.query(models.User).filter(models.User.id == loan.user_id).first()
    if not user:
        logger.info("POST /loans - owner user_id=%s not found", loan.user_id)
        raise HTTPException(status_code=404, detail="User not found")

    db_loan = models.Loan(**loan.model_dump())
    db.add(db_loan)
    db.commit()
    db.refresh(db_loan)
    logger.info("POST /loans - created loan id=%s", db_loan.id)
    return db_loan


@app.get("/loans", response_model=List[schemas.LoanRead])
def list_loans(db: Session = Depends(get_db)):
    """Return all loans."""
    loans = db.query(models.Loan).all()
    logger.info("GET /loans - returned count=%s", len(loans))
    return loans


@app.get("/loans/{loan_id}", response_model=schemas.LoanRead)
def get_loan(loan_id: int, db: Session = Depends(get_db)):
    """Return a single loan by id including shared user ids."""
    logger.info("GET /loans/%s - fetching", loan_id)
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        logger.info("GET /loans/%s - not found", loan_id)
        raise HTTPException(status_code=404, detail="Loan not found")
    logger.info("GET /loans/%s - found", loan_id)
    return schemas.LoanRead(
        id=loan.id,
        user_id=loan.user_id,
        amount=loan.amount,
        annual_interest_rate=loan.annual_interest_rate,
        loan_term_in_months=loan.loan_term_in_months,
        shared_user_ids=[u.id for u in loan.shared_users],
    )


@app.post("/loans/{loan_id}/share", response_model=schemas.LoanRead)
def share_loan(loan_id: int, payload: schemas.LoanShareRequest, db: Session = Depends(get_db)):
    """Grant another user read-only access to an existing loan."""
    logger.info("POST /loans/%s/share - sharing with user_id=%s", loan_id, payload.user_id)
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        logger.info("POST /loans/%s/share - loan not found", loan_id)
        raise HTTPException(status_code=404, detail="Loan not found")

    user_to_share = db.query(models.User).filter(models.User.id == payload.user_id).first()
    if not user_to_share:
        logger.info("POST /loans/%s/share - user_id=%s not found", loan_id, payload.user_id)
        raise HTTPException(status_code=404, detail="User to share with not found")

    if user_to_share.id == loan.user_id:
        logger.info("POST /loans/%s/share - cannot share to owner user_id=%s", loan_id, payload.user_id)
        raise HTTPException(status_code=400, detail="Owner already has access to this loan")

    if user_to_share in loan.shared_users:
        logger.info("POST /loans/%s/share - already shared to user_id=%s", loan_id, payload.user_id)
        raise HTTPException(status_code=400, detail="Loan already shared with this user")

    loan.shared_users.append(user_to_share)
    db.add(loan)
    db.commit()
    db.refresh(loan)
    logger.info("POST /loans/%s/share - now shared_count=%s", loan_id, len(loan.shared_users))

    return schemas.LoanRead(
        id=loan.id,
        user_id=loan.user_id,
        amount=loan.amount,
        annual_interest_rate=loan.annual_interest_rate,
        loan_term_in_months=loan.loan_term_in_months,
        shared_user_ids=[u.id for u in loan.shared_users],
    )


@app.get("/loans/{loan_id}/schedule", response_model=List[schemas.LoanScheduleItem])
def get_loan_schedule(loan_id: int, db: Session = Depends(get_db)):
    """Return the amortization schedule with monthly payment and remaining balance."""
    logger.info("GET /loans/%s/schedule - computing schedule", loan_id)
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        logger.info("GET /loans/%s/schedule - loan not found", loan_id)
        raise HTTPException(status_code=404, detail="Loan not found")

    n = loan.loan_term_in_months
    if n <= 0:
        logger.info("GET /loans/%s/schedule - invalid term=%s", loan_id, n)
        raise HTTPException(status_code=400, detail="Loan term must be positive")

    P = Decimal(str(loan.amount))
    r_monthly = Decimal(str(loan.annual_interest_rate)) / Decimal("100") / Decimal("12")
    monthly_payment = _compute_monthly_payment(P, r_monthly, n)
    logger.info(
        "GET /loans/%s/schedule - amount=%s rate=%s term=%s monthly_payment=%s",
        loan_id,
        P,
        r_monthly,
        n,
        monthly_payment,
    )

    schedule: List[schemas.LoanScheduleItem] = []
    remaining = P

    for i in range(1, n + 1):
        interest = Decimal("0") if r_monthly == 0 else _to_cents(remaining * r_monthly)
        principal_payment = monthly_payment - interest
        if i == n:
            principal_payment = remaining
            interest = monthly_payment - principal_payment
        if principal_payment > remaining:
            principal_payment = remaining
        remaining = remaining - principal_payment

        schedule.append(
            schemas.LoanScheduleItem(
                month=i,
                remaining_balance=float(_to_cents(remaining)),
                monthly_payment=float(monthly_payment),
            )
        )

    logger.info("GET /loans/%s/schedule - generated rows=%s", loan_id, len(schedule))
    return schedule


@app.get("/loans/{loan_id}/summary", response_model=schemas.LoanSummary)
def get_loan_summary(loan_id: int, month: int, db: Session = Depends(get_db)):
    """Return remaining principal, total principal, and total interest paid at a given month."""
    logger.info("GET /loans/%s/summary - month=%s", loan_id, month)
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        logger.info("GET /loans/%s/summary - loan not found", loan_id)
        raise HTTPException(status_code=404, detail="Loan not found")

    n = loan.loan_term_in_months
    if n <= 0:
        logger.info("GET /loans/%s/summary - invalid term=%s", loan_id, n)
        raise HTTPException(status_code=400, detail="Loan term must be positive")
    if month < 0 or month > n:
        logger.info("GET /loans/%s/summary - invalid month=%s (term=%s)", loan_id, month, n)
        raise HTTPException(status_code=400, detail=f"month must be between 0 and {n}")

    P = Decimal(str(loan.amount))
    r_monthly = Decimal(str(loan.annual_interest_rate)) / Decimal("100") / Decimal("12")

    remaining = current_principal_balance_at_month(P, r_monthly, n, month)
    total_principal = total_principal_paid_at_month(P, r_monthly, n, month)
    total_interest = total_interest_paid_at_month(P, r_monthly, n, month)

    logger.info(
        "GET /loans/%s/summary - remaining=%s principal_paid=%s interest_paid=%s",
        loan_id,
        remaining,
        total_principal,
        total_interest,
    )

    return schemas.LoanSummary(
        current_principal_balance=float(remaining),
        total_principal_paid=float(total_principal),
        total_interest_paid=float(total_interest),
    )