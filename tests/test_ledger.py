import website_ledger as wl


def test_seven_percent_fee_and_93_percent_payout():
    assert wl.split_sale(10000) == {"amount_cents": 10000, "platform_fee_cents": 700,
                                    "builder_payout_cents": 9300}


def test_any_fraction_of_a_cent_rounds_up():
    assert wl.split_sale(1999)["platform_fee_cents"] == 140   # 139.93 -> 140
    assert wl.split_sale(10001)["platform_fee_cents"] == 701  # 700.07 -> 701
    r = wl.split_sale(1999)
    assert r["platform_fee_cents"] + r["builder_payout_cents"] == 1999


def test_one_dollar_is_the_minimum_paid_sale():
    assert wl.split_sale(100)["platform_fee_cents"] == 7
    assert wl.split_sale(99) == {"error": "below_minimum_sale"}


def test_free_plan_is_allowed_with_no_fee_or_payout():
    assert wl.split_sale(0) == {"amount_cents": 0, "platform_fee_cents": 0, "builder_payout_cents": 0}


def test_rejects_bad_amounts():
    assert "error" in wl.split_sale(-5)
    assert "error" in wl.split_sale(10.5)
    assert "error" in wl.split_sale(True)


def test_bundle_fee_on_total_and_pool_allocated_by_list_price():
    # $10 + $20 plans sold as one $25 bundle. Fee = 7% of 2500 = 175 cents exactly.
    r = wl.split_bundle(2500, [1000, 2000])
    assert r["platform_fee_cents"] == 175
    assert r["builder_pool_cents"] == 2325
    assert sum(r["per_plan_payout_cents"]) == 2325


def test_bundle_allocation_sums_exactly_with_largest_remainder():
    r = wl.split_bundle(2500, [1000, 2000])
    assert r["per_plan_payout_cents"] == [775, 1550]


def test_free_bundle_pays_nothing():
    r = wl.split_bundle(0, [1000, 2000])
    assert r["platform_fee_cents"] == 0
    assert r["per_plan_payout_cents"] == [0, 0]


def test_bundle_below_minimum_rejected_unless_free():
    assert wl.split_bundle(50, [1000])["error"] == "below_minimum_sale"


def test_bundle_rejects_bad_inputs():
    assert "error" in wl.split_bundle(1000, [])
    assert "error" in wl.split_bundle(1000, [0])
