from fastapi.testclient import TestClient
from decimal import Decimal, ROUND_HALF_UP
import pytest


def _create_user(client: TestClient, username: str, email: str) -> int:
    r = client.post("/users", json={"username": username, "email": email})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_loan(client: TestClient, owner_id: int, amount=10000.0, rate=6.0, term=12) -> int:
    r = client.post(
        "/loans",
        json={
            "user_id": owner_id,
            "amount": amount,
            "annual_interest_rate": rate,
            "loan_term_in_months": term,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_and_list_loans(client: TestClient):
    owner_id = _create_user(client, "owner", "owner@example.com")
    loan_id = _create_loan(client, owner_id)

    r_list = client.get("/loans")
    assert r_list.status_code == 200
    loans = r_list.json()
    assert len(loans) == 1
    assert loans[0]["id"] == loan_id

    r_get = client.get(f"/loans/{loan_id}")
    assert r_get.status_code == 200
    data = r_get.json()
    assert data["user_id"] == owner_id


def test_schedule_length_and_fields(client: TestClient):
    owner_id = _create_user(client, "s1", "s1@example.com")
    loan_id = _create_loan(client, owner_id, amount=1200.0, rate=0.0, term=12)

    r = client.get(f"/loans/{loan_id}/schedule")
    assert r.status_code == 200
    schedule = r.json()
    assert len(schedule) == 12
    first = schedule[0]
    assert set(first.keys()) == {"month", "remaining_balance", "monthly_payment"}


def test_summary_validations_and_values(client: TestClient):
    owner_id = _create_user(client, "s2", "s2@example.com")
    loan_id = _create_loan(client, owner_id, amount=1000.0, rate=12.0, term=10)

    # month range check
    r_bad = client.get(f"/loans/{loan_id}/summary", params={"month": 999})
    assert r_bad.status_code == 400

    # month 0: all principal remaining, nothing paid
    r0 = client.get(f"/loans/{loan_id}/summary", params={"month": 0})
    assert r0.status_code == 200
    d0 = r0.json()
    assert d0["total_principal_paid"] == 0.0
    assert d0["total_interest_paid"] == 0.0

    # some month > 0 within term
    r5 = client.get(f"/loans/{loan_id}/summary", params={"month": 5})
    assert r5.status_code == 200
    d5 = r5.json()
    assert d5["current_principal_balance"] >= 0.0


def test_share_same_user_twice_errors(client: TestClient):
    owner_id = _create_user(client, "share_owner", "share_owner@example.com")
    other_id = _create_user(client, "share_viewer", "share_viewer@example.com")
    loan_id = _create_loan(client, owner_id)

    r1 = client.post(f"/loans/{loan_id}/share", json={"user_id": other_id})
    assert r1.status_code == 200

    r2 = client.post(f"/loans/{loan_id}/share", json={"user_id": other_id})
    assert r2.status_code == 400

    # owner cannot be shared to
    r3 = client.post(f"/loans/{loan_id}/share", json={"user_id": owner_id})
    assert r3.status_code == 400


def test_summary_month_param_validation(client: TestClient):
    owner_id = _create_user(client, "sumv", "sumv@example.com")
    loan_id = _create_loan(client, owner_id, amount=5000.0, rate=5.0, term=24)

    # missing month -> 422
    r_missing = client.get(f"/loans/{loan_id}/summary")
    assert r_missing.status_code == 422

    # negative month -> 400
    r_neg = client.get(f"/loans/{loan_id}/summary", params={"month": -1})
    assert r_neg.status_code == 400

    # month beyond term -> 400
    r_over = client.get(f"/loans/{loan_id}/summary", params={"month": 25})
    assert r_over.status_code == 400

    # non-integer month -> 422
    r_str = client.get(f"/loans/{loan_id}/summary", params={"month": "abc"})
    assert r_str.status_code == 422


def test_summary_zero_interest_linear_behavior(client: TestClient):
    owner_id = _create_user(client, "zeroi", "zeroi@example.com")
    amount = Decimal("1200.0")
    term = 12
    loan_id = _create_loan(client, owner_id, amount=float(amount), rate=0.0, term=term)

    # month 6: half principal paid, half remaining (with 2-dec rounding)
    r6 = client.get(f"/loans/{loan_id}/summary", params={"month": 6})
    assert r6.status_code == 200
    d6 = r6.json()
    total_principal_paid = Decimal(str(d6["total_principal_paid"]))
    current_balance = Decimal(str(d6["current_principal_balance"]))
    assert total_principal_paid == (amount * Decimal(6) / Decimal(term)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert current_balance == (amount * (Decimal(1) - Decimal(6) / Decimal(term))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert Decimal(str(d6["total_interest_paid"])) == Decimal("0.00")


def test_schedule_term_validation_and_monotonicity(client: TestClient):
    owner_id = _create_user(client, "schedv", "schedv@example.com")

    # Term 0 should be rejected by endpoint
    loan_zero_term = _create_loan(client, owner_id, amount=1000.0, rate=5.0, term=0)
    r_zero = client.get(f"/loans/{loan_zero_term}/schedule")
    assert r_zero.status_code == 400

    # Valid loan: payment constant and balance decreases to ~0
    loan_id = _create_loan(client, owner_id, amount=10000.0, rate=6.0, term=24)
    r = client.get(f"/loans/{loan_id}/schedule")
    assert r.status_code == 200
    schedule = r.json()
    payments = [Decimal(str(row["monthly_payment"])) for row in schedule]
    balances = [Decimal(str(row["remaining_balance"])) for row in schedule]

    assert all(abs(pay - payments[0]) < Decimal("0.000001") for pay in payments)
    # Non-increasing balances
    assert all(balances[i] <= balances[i - 1] + Decimal("0.000000001") for i in range(1, len(balances)))
    # Last balance should be zero (clamped)
    assert balances[-1].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal("0.00")


# --------------- Happy path tests ---------------

def _to_cents(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _expected_amortization(principal: float, annual_rate: float, term_months: int):
    """Yield tuples of (month_index, payment, interest, principal_payment, remaining)
    Uses the same rounding approach as the summary endpoint: payment rounded to cents,
    interest per month rounded to cents, principal = payment - interest, clamp final.
    """
    P = Decimal(str(principal))
    r = Decimal(str(annual_rate)) / Decimal("100") / Decimal("12")
    n = term_months
    if r == 0:
        payment = _to_cents(P / Decimal(n))
    else:
        one_plus_r_pow_n = (Decimal("1") + r) ** n
        payment = _to_cents(P * (r * one_plus_r_pow_n) / (one_plus_r_pow_n - Decimal("1")))

    remaining = P
    for m in range(1, n + 1):
        interest = Decimal("0") if r == 0 else _to_cents(remaining * r)
        principal_paid = payment - interest
        if m == n:
            principal_paid = remaining
            interest = payment - principal_paid
        if principal_paid > remaining:
            principal_paid = remaining
        remaining = remaining - principal_paid
        yield m, payment, interest, principal_paid, remaining


def test_schedule_happy_path_matches_payment_formula(client: TestClient):
    owner_id = _create_user(client, "schedhappy", "schedhappy@example.com")
    amount = 15000.0
    rate = 7.5
    term = 36
    loan_id = _create_loan(client, owner_id, amount=amount, rate=rate, term=term)

    r = client.get(f"/loans/{loan_id}/schedule")
    assert r.status_code == 200
    schedule = r.json()

    # Expected monthly payment to 2 decimals
    exp = list(_expected_amortization(amount, rate, term))
    expected_payment = exp[0][1]  # Decimal
    schedule_payment = Decimal(str(schedule[0]["monthly_payment"]))
    assert schedule_payment == expected_payment

    # Final remaining balance ~ 0
    assert Decimal(str(schedule[-1]["remaining_balance"])) == Decimal("0.00")


def test_summary_happy_path_matches_amortization(client: TestClient):
    owner_id = _create_user(client, "sumhappy", "sumhappy@example.com")
    amount = 12345.67
    rate = 4.25
    term = 24
    loan_id = _create_loan(client, owner_id, amount=amount, rate=rate, term=term)

    amort = list(_expected_amortization(amount, rate, term))

    # Check month 1, mid-term, and final term
    for month in [1, term // 2, term]:
        total_interest = sum(row[2] for row in amort[:month])  # Decimal
        total_principal = sum(row[3] for row in amort[:month])  # Decimal
        remaining = amort[month - 1][4]  # Decimal

        r = client.get(f"/loans/{loan_id}/summary", params={"month": month})
        assert r.status_code == 200
        data = r.json()

        cur_bal = Decimal(str(data["current_principal_balance"]))
        tot_prin = Decimal(str(data["total_principal_paid"]))
        tot_int = Decimal(str(data["total_interest_paid"]))

        assert cur_bal == _to_cents(remaining)
        assert tot_prin == _to_cents(total_principal)
        assert tot_int == _to_cents(total_interest)

    # At term: all principal paid
    r_final = client.get(f"/loans/{loan_id}/summary", params={"month": term})
    d_final = r_final.json()
    assert Decimal(str(d_final["current_principal_balance"])) == Decimal("0.00")
    assert Decimal(str(d_final["total_principal_paid"])) == _to_cents(Decimal(str(amount)))


# --------------- Financial accuracy (parametrized) ---------------

@pytest.mark.parametrize(
    "amount, rate, term",
    [
        (10000.0, 6.0, 12),
        (250000.0, 5.5, 360),
        (5000.0, 0.99, 24),
        (9999.99, 9.99, 48),
    ],
)
def test_financial_accuracy_final_totals(client: TestClient, amount, rate, term):
    owner_id = _create_user(client, f"fin_{amount}_{rate}_{term}", f"fin_{amount}_{rate}_{term}@example.com")
    loan_id = _create_loan(client, owner_id, amount=amount, rate=rate, term=term)

    # Endpoint summary at term
    r = client.get(f"/loans/{loan_id}/summary", params={"month": term})
    assert r.status_code == 200
    summary = r.json()

    amort = list(_expected_amortization(amount, rate, term))
    total_interest_expected = _to_cents(sum(row[2] for row in amort))  # Decimal

    # Principal paid equals original principal
    assert Decimal(str(summary["total_principal_paid"])) == _to_cents(Decimal(str(amount)))
    # Remaining is zero
    assert Decimal(str(summary["current_principal_balance"])) == Decimal("0.00")
    # Interest equals expected amortized interest
    assert Decimal(str(summary["total_interest_paid"])) == total_interest_expected


@pytest.mark.parametrize(
    "amount, rate, term",
    [
        (10000.0, 6.0, 12),
        (12345.67, 4.25, 24),
        (8000.0, 3.2, 60),
    ],
)
def test_financial_accuracy_payment_consistency(client: TestClient, amount, rate, term):
    owner_id = _create_user(client, f"pay_{amount}_{rate}_{term}", f"pay_{amount}_{rate}_{term}@example.com")
    loan_id = _create_loan(client, owner_id, amount=amount, rate=rate, term=term)

    sched = client.get(f"/loans/{loan_id}/schedule").json()
    payment = Decimal(str(sched[0]["monthly_payment"]))
    total_paid = payment * Decimal(term)

    final_summary = client.get(f"/loans/{loan_id}/summary", params={"month": term}).json()
    expected_total = Decimal(str(amount)) + Decimal(str(final_summary["total_interest_paid"]))

    # Allow tiny rounding differences (<= 10 cents across full term)
    assert abs(total_paid - expected_total) <= Decimal("0.10")


def test_financial_identity_by_month(client: TestClient):
    amount = Decimal("54321.0")
    rate = 7.25
    term = 36
    owner_id = _create_user(client, "ident_user", "ident@example.com")
    loan_id = _create_loan(client, owner_id, amount=float(amount), rate=rate, term=term)

    for month in [0, 1, term // 3, term // 2, term]:
        data = client.get(f"/loans/{loan_id}/summary", params={"month": month}).json()
        # principal_paid + remaining == original principal (to cents)
        total = Decimal(str(data["total_principal_paid"])) + Decimal(str(data["current_principal_balance"]))
        assert total == _to_cents(amount)
