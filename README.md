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

### Users
- POST `/users` → create user
  - Body: `{ "username": "alice", "email": "alice@example.com" }`
- GET `/users` → list users
- GET `/users/{user_id}/loans` → list loans owned by a user

### Loans
- POST `/loans` → create loan
  - Body: `{ "user_id": 1, "amount": 10000, "annual_interest_rate": 5.5, "loan_term_in_months": 36 }`
- GET `/loans` → list all loans
- GET `/loans/{loan_id}` → get loan details (includes `shared_user_ids`)
- POST `/loans/{loan_id}/share` → share loan read-access with another user
  - Body: `{ "user_id": 2 }`
  - Errors:
    - 404 if loan or user not found
    - 400 if sharing to the owner
    - 400 if already shared to that user
- GET `/loans/{loan_id}/schedule` → amortization schedule
  - Response: array of `{ month, remaining_balance, monthly_payment }` for each month
- GET `/loans/{loan_id}/summary?month=N` → loan summary at month N
  - Response: `{ current_principal_balance, total_principal_paid, total_interest_paid }`
  - Validates `0 <= month <= loan_term_in_months`

## Financial formulas and rounding

- **Monthly rate**: \( r = \frac{\text{annual\_interest\_rate}}{100 \cdot 12} \)
- **Fixed monthly payment** (if \( r > 0 \)):
  \[ M = P \cdot \frac{r (1 + r)^n}{(1 + r)^n - 1} \]
- **Zero-rate monthly payment** (if \( r = 0 \)):
  \[ M = \frac{P}{n} \]
- **Per-period interest**:
  \[ \text{interest}_t = \text{remaining}_{t-1} \cdot r \]
- **Per-period principal**:
  \[ \text{principal}_t = M - \text{interest}_t \]
- **Remaining balance update**:
  \[ \text{remaining}_t = \text{remaining}_{t-1} - \text{principal}_t \]
- **Final month adjustment**: on month \( n \), principal is forced to exactly clear the remaining balance and interest is adjusted so \( M = \text{principal}_n + \text{interest}_n \).
- **Rounding**: all monetary values are computed with Python `Decimal` and rounded to cents using `ROUND_HALF_UP` per period.

## Tests

```bash
pytest -q
```

- Tests use a temporary SQLite database.
- Financial tests use Decimal arithmetic and assert cent-accurate results.

## Improvements
Adding OAUTH2, currently there is no authentication for users as I operated under the assumption that the loan logic was the focus of this exercise 
Adding Admins/ Administrative Endpoints
Adding Ability to pay loans by users 
Adding Acceptance Tests
Adding CI/CD using Github Actions 
Adding linter to enforce PEP8 Standards / Pre-commit hook
Adding further code documentation

