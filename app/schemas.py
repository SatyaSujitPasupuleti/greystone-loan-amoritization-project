from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class LoanBase(BaseModel):
    amount: float
    annual_interest_rate: float
    loan_term_in_months: int


class LoanCreate(LoanBase):
    user_id: int


class LoanRead(LoanBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class LoanScheduleItem(BaseModel):
    month: int
    remaining_balance: float
    monthly_payment: float