from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

from . import models, schemas
from .database import engine, get_db

# Create tables on startup (simple dev setup)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Loan Amori API")


# User endpoints
@app.post("/users", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(models.User)
        .filter((models.User.username == user.username) | (models.User.email == user.email))
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists")

    db_user = models.User(**user.model_dump())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.get("/users", response_model=List[schemas.UserRead])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()


@app.get("/users/{user_id}/loans", response_model=List[schemas.LoanRead])
def list_loans_for_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return db.query(models.Loan).filter(models.Loan.user_id == user_id).all()


# Loan endpoints
@app.post("/loans", response_model=schemas.LoanRead, status_code=status.HTTP_201_CREATED)
def create_loan(loan: schemas.LoanCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == loan.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db_loan = models.Loan(**loan.model_dump())
    db.add(db_loan)
    db.commit()
    db.refresh(db_loan)
    return db_loan


@app.get("/loans", response_model=List[schemas.LoanRead])
def list_loans(db: Session = Depends(get_db)):
    return db.query(models.Loan).all()


@app.get("/loans/{loan_id}/schedule", response_model=List[schemas.LoanScheduleItem])
def get_loan_schedule(loan_id: int, db: Session = Depends(get_db)):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    principal = loan.amount
    n = loan.loan_term_in_months
    r_monthly = loan.annual_interest_rate / 100.0 / 12.0

    if n <= 0:
        raise HTTPException(status_code=400, detail="Loan term must be positive")

    if r_monthly == 0:
        monthly_payment = principal / n
    else:
        # Standard amortization monthly payment formula
        monthly_payment = principal * (r_monthly * (1 + r_monthly) ** n) / ((1 + r_monthly) ** n - 1)

    schedule: List[schemas.LoanScheduleItem] = []
    remaining = principal

    for month in range(1, n + 1):
        if r_monthly == 0:
            interest = 0.0
        else:
            interest = remaining * r_monthly
        principal_payment = monthly_payment - interest
        # Prevent negative remaining balance in last payment due to rounding
        remaining = max(0.0, remaining - principal_payment)

        schedule.append(
            schemas.LoanScheduleItem(
                month=month,
                remaining_balance=round(remaining, 2),
                monthly_payment=round(monthly_payment, 2),
            )
        )

    return schedule