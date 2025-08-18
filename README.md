# Loan Amori API

Simple FastAPI project using SQLAlchemy and SQLite.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

- Open `http://127.0.0.1:8000/docs` for Swagger UI.

## API

- POST `/users` -> create user: `{ "username": "alice", "email": "alice@example.com" }`
- GET `/users` -> list users
- POST `/loans` -> create loan: `{ "amount": 10000, "annual_interest_rate": 5.5, "loan_term_in_months": 36 }`
- GET `/loans` -> list loans
