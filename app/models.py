from sqlalchemy import Column, Integer, String, Float, ForeignKey, Table
from sqlalchemy.orm import relationship

from .database import Base


# Association table enabling many-to-many sharing of loans with users (read access)
loan_shares = Table(
    "loan_shares",
    Base.metadata,
    Column("loan_id", Integer, ForeignKey("loans.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)

    loans = relationship(
        "Loan",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Loans that this user has been granted read access to (not owned by them)
    shared_loans = relationship(
        "Loan",
        secondary=loan_shares,
        back_populates="shared_users",
    )


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    annual_interest_rate = Column(Float, nullable=False)
    loan_term_in_months = Column(Integer, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user = relationship("User", back_populates="loans")

    # Users who have been granted read access to this loan (besides the owner)
    shared_users = relationship(
        "User",
        secondary=loan_shares,
        back_populates="shared_loans",
    )
