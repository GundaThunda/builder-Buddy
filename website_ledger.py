"""
Sale split: platform fee and builder payout.

Sales route through the platform account first. The platform keeps PLATFORM_FEE_RATE_PERCENT
of each sale, rounded up to the next cent, and the builder receives the remainder. Money is
kept in integer cents throughout, so the amounts always sum exactly to the sale.

Rules (owner-confirmed):
  - Minimum paid sale is MIN_PAID_SALE_CENTS ($1.00).
  - A free plan (0 cents) is allowed and produces no fee and no payout.
  - Plans may be bundled into one deal at a single price. The fee applies to the bundle total,
    and the builder pool is divided among the bundled plans in proportion to their list prices.
"""

PLATFORM_FEE_RATE_PERCENT = 7
MIN_PAID_SALE_CENTS = 100


def _fee(amount_cents: int) -> int:
    # Ceiling in integer math: any fractional cent rounds up.
    return (amount_cents * PLATFORM_FEE_RATE_PERCENT + 99) // 100


def split_sale(amount_cents: int) -> dict:
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool):
        return {"error": "amount_cents must be an integer"}
    if amount_cents < 0:
        return {"error": "amount_cents must not be negative"}
    if amount_cents == 0:
        return {"amount_cents": 0, "platform_fee_cents": 0, "builder_payout_cents": 0}
    if amount_cents < MIN_PAID_SALE_CENTS:
        return {"error": "below_minimum_sale"}
    fee = _fee(amount_cents)
    return {
        "amount_cents": amount_cents,
        "platform_fee_cents": fee,
        "builder_payout_cents": amount_cents - fee,
    }


def split_bundle(bundle_cents: int, list_prices_cents: list) -> dict:
    """
    Split one bundle sale across its plans.
    list_prices_cents: each bundled plan's list price, in order. Used only for allocation.
    Returns per-plan payouts that sum exactly to the builder pool.
    """
    if not isinstance(bundle_cents, int) or isinstance(bundle_cents, bool) or bundle_cents < 0:
        return {"error": "bundle_cents must be a non-negative integer"}
    if not list_prices_cents:
        return {"error": "bundle needs at least one plan"}
    if any(not isinstance(p, int) or isinstance(p, bool) or p <= 0 for p in list_prices_cents):
        return {"error": "each list price must be a positive integer"}
    if bundle_cents != 0 and bundle_cents < MIN_PAID_SALE_CENTS:
        return {"error": "below_minimum_sale"}

    if bundle_cents == 0:
        fee, pool = 0, 0
    else:
        fee = _fee(bundle_cents)
        pool = bundle_cents - fee

    total_list = sum(list_prices_cents)
    # Largest-remainder allocation so the per-plan payouts sum exactly to the pool.
    raw = [pool * p / total_list for p in list_prices_cents]
    base = [int(r) for r in raw]
    leftover = pool - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:leftover]:
        base[i] += 1

    return {
        "bundle_cents": bundle_cents,
        "platform_fee_cents": fee,
        "builder_pool_cents": pool,
        "per_plan_payout_cents": base,
    }
