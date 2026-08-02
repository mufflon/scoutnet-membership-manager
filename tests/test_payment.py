from __future__ import annotations

import pytest

from karverktyg.scoutnet.models import PaymentBucket, classify_payment


@pytest.mark.parametrize(
    "code,bucket",
    [
        ("paid", PaymentBucket.SETTLED),
        ("not_invoiced", PaymentBucket.NOT_BILLED),
        ("unpaid_overdue_reminded", PaymentBucket.OUTSTANDING),
        ("paid_partial_credit", PaymentBucket.OUTSTANDING),  # paid wrong amount, not settled
        ("some_future_code", PaymentBucket.UNKNOWN),  # unseen -> review, never guessed
        ("unpaid", PaymentBucket.UNKNOWN),  # plausible but unobserved -> review
        (None, PaymentBucket.UNKNOWN),
    ],
)
def test_classify_payment(code, bucket):
    assert classify_payment(code) is bucket
