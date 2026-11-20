"""
Sale split: platform fee and builder payout.

Sales route through the platform account first. The platform keeps PLATFORM_FEE_RATE of
each sale and pays the rest to the builder. Money is kept in integer cents throughout.

Rounding: any fraction of a cent in the fee rounds up to the next cent, and the builder
receives the remainder, so the two amounts always sum exactly to the sale. Owner-confirmed.
"""

PLATFORM_FEE_RATE_PERCENT = 7  # 7 cents on the dollar, per owner decision


def split_sale(amount_cents: int) -> dict:
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool):
        return {"error": "amount_cents must be an integer"}
    if amount_cents <= 0:
        return {"error": "amount_cents must be positive"}
    # Ceiling in integer math: any fractional cent rounds up.
    fee = (amount_cents * PLATFORM_FEE_RATE_PERCENT + 99) // 100
    return {
        "amount_cents": amount_cents,
        "platform_fee_cents": fee,
        "builder_payout_cents": amount_cents - fee,
    }
