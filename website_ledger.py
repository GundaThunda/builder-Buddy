"""
Sale split: platform fee and builder payout.

Sales route through the platform account first. The platform keeps PLATFORM_FEE_RATE of
each sale and pays the rest to the builder. Money is kept in integer cents throughout.

Rounding: the fee is rounded half-up to the cent, and the builder receives the remainder,
so the two amounts always sum exactly to the sale. This is a proposed rule, not confirmed.
"""

PLATFORM_FEE_RATE_PERCENT = 7  # 7 cents on the dollar, per owner decision


def split_sale(amount_cents: int) -> dict:
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool):
        return {"error": "amount_cents must be an integer"}
    if amount_cents <= 0:
        return {"error": "amount_cents must be positive"}
    # Half-up rounding in integer math: (x*7 + 50) // 100
    fee = (amount_cents * PLATFORM_FEE_RATE_PERCENT + 50) // 100
    return {
        "amount_cents": amount_cents,
        "platform_fee_cents": fee,
        "builder_payout_cents": amount_cents - fee,
    }
