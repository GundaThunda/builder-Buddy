import website_ledger as wl


def test_seven_percent_fee_and_93_percent_payout():
    r = wl.split_sale(10000)  # $100.00
    assert r == {"amount_cents": 10000, "platform_fee_cents": 700, "builder_payout_cents": 9300}


def test_half_up_rounding_and_exact_total():
    r = wl.split_sale(1999)  # 139.93 -> 140
    assert r["platform_fee_cents"] == 140
    assert r["builder_payout_cents"] == 1859
    assert r["platform_fee_cents"] + r["builder_payout_cents"] == 1999


def test_half_cent_rounds_up():
    # 7% of 50 cents = 3.5 cents -> 4
    assert wl.split_sale(50)["platform_fee_cents"] == 4


def test_rejects_bad_amounts():
    assert "error" in wl.split_sale(0)
    assert "error" in wl.split_sale(-5)
    assert "error" in wl.split_sale(10.5)
    assert "error" in wl.split_sale(True)
