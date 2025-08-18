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
