from typing import Optional, List
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
    shared_user_ids: Optional[List[int]] = None

    model_config = ConfigDict(from_attributes=True)


class LoanScheduleItem(BaseModel):
    month: int
    remaining_balance: float
    monthly_payment: float


class LoanSummary(BaseModel):
    current_principal_balance: float
    total_principal_paid: float
    total_interest_paid: float


class LoanShareRequest(BaseModel):
    user_id: int