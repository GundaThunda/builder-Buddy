"""
Ron G plugin billing via Stripe.

Config comes only from environment variables. Nothing secret is stored in the repo:
  STRIPE_SECRET_KEY        API secret key
  STRIPE_WEBHOOK_SECRET    signing secret for the webhook endpoint
  STRIPE_RON_G_PRICE_ID    price ID of the Ron G subscription
  APP_BASE_URL             where Stripe sends the buyer back, e.g. https://example.com

Subscription state is driven by webhooks, not by the checkout redirect. The subscriber's
Builder Buddy handle travels in subscription metadata, so a webhook can find the account.
"""
import os

import stripe

import website_ron_g_access as access

ACTIVE_STATUSES = {"active", "trialing"}
INACTIVE_STATUSES = {"canceled", "unpaid", "incomplete_expired", "past_due"}


class BillingNotConfigured(Exception):
    pass


def _config() -> dict:
    cfg = {
        "secret_key": os.environ.get("STRIPE_SECRET_KEY", ""),
        "webhook_secret": os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        "price_id": os.environ.get("STRIPE_RON_G_PRICE_ID", ""),
        "base_url": os.environ.get("APP_BASE_URL", "").rstrip("/"),
    }
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        raise BillingNotConfigured(",".join(missing))
    return cfg


def create_checkout_url(handle: str) -> str:
    cfg = _config()
    session = stripe.checkout.Session.create({
        "mode": "subscription",
        "line_items": [{"price": cfg["price_id"], "quantity": 1}],
        "client_reference_id": handle,
        "subscription_data": {"metadata": {"handle": handle}},
        "success_url": f"{cfg['base_url']}/ron-g/billing/success",
        "cancel_url": f"{cfg['base_url']}/ron-g/billing/cancel",
        "api_key": cfg["secret_key"],
    })
    return session.url


def handle_webhook(payload: bytes, signature: str) -> dict:
    """Verify the signature, then update access. Raises on a bad signature."""
    cfg = _config()
    event = stripe.Webhook.construct_event(payload, signature, cfg["webhook_secret"])
    if event["type"] not in ("customer.subscription.created",
                             "customer.subscription.updated",
                             "customer.subscription.deleted"):
        return {"ignored": event["type"]}
    sub = event["data"]["object"]
    handle = (sub.get("metadata") or {}).get("handle")
    if not handle:
        return {"ignored": "no_handle"}
    status = sub.get("status")
    if event["type"] == "customer.subscription.deleted" or status in INACTIVE_STATUSES:
        access.set_subscribed(handle, False)
        return {"handle": handle, "subscribed": False}
    if status in ACTIVE_STATUSES:
        access.set_subscribed(handle, True)
        return {"handle": handle, "subscribed": True}
    return {"ignored": status}
