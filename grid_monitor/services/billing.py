"""Durable sandbox billing. Web requests enqueue; a separate CLI worker verifies."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
import time

import click
from flask import current_app
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from grid_monitor.billing_models import BillingAccount, BillingEvent, BillingInvoice, BillingPayment
from grid_monitor.extensions import db
from grid_monitor.services.paystack import BillingError, identifier, provider, provider_url, sandbox_enabled, test_object, validate_plan
from grid_monitor.services.subscriptions import PRICING_VERSION, PRO_AMOUNTS_MINOR
from grid_monitor.subscription_models import SubscriptionPlanPrice, User, UserSubscription, utc_now

PROVIDER = "paystack_test"
LEASE_SECONDS = 300
SUPPORTED_EVENTS = {"charge.success", "subscription.create", "subscription.not_renew",
                    "subscription.disable", "invoice.create", "invoice.update", "invoice.payment_failed"}


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def timestamp(value, *, optional=False):
    if value is None and optional:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (AttributeError, ValueError, TypeError):
        raise BillingError("invalid_provider_timestamp", False) from None


def monthly_period(start, end):
    start, end = timestamp(start), timestamp(end)
    if not timedelta(days=20) <= end - start <= timedelta(days=32):
        raise BillingError("invalid_billing_period", False)
    return start, end


def _insert_event(digest, event_type, payload):
    dialect = db.engine.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(BillingEvent).values(digest=digest, event_type=event_type, payload=payload,
        status="pending", attempts=0, available_at=utc_now(), received_at=utc_now())
    inserted = db.session.execute(stmt.on_conflict_do_nothing(index_elements=["digest"])
                                  .returning(BillingEvent.digest)).scalar_one_or_none()
    db.session.commit()
    return inserted is not None


def enqueue_internal(event_type, payload, key):
    return _insert_event(hashlib.sha256(key.encode()).hexdigest(), event_type, payload)


def _invoice_fields(data):
    # Persist billing identifiers only, never raw authorization/card data or email tokens.
    sub = data.get("subscription") or {}
    tx = data.get("transaction")
    transaction = ({key: tx.get(key) for key in ("id", "reference")} if isinstance(tx, dict) else tx)
    return {key: data.get(key) for key in ("invoice_code", "amount", "period_start", "period_end",
            "status", "paid", "paid_at", "domain")} | {
        "subscription_code": sub.get("subscription_code") if isinstance(sub, dict) else None,
        "transaction": transaction}


def receive_webhook(raw, signature):
    secret = current_app.config["PAYSTACK_SECRET_KEY"].encode()
    expected = hmac.new(secret, raw, hashlib.sha512).hexdigest()
    if not isinstance(signature, str) or not re.fullmatch(r"[a-fA-F0-9]{128}", signature) or not hmac.compare_digest(expected, signature.lower()):
        raise BillingError("invalid_webhook_signature", False)
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise BillingError("invalid_webhook_json", False) from None
    if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
        raise BillingError("invalid_webhook_json", False)
    kind, data = event.get("event"), event["data"]
    if kind not in SUPPORTED_EVENTS:
        return False
    if data.get("domain") != "test":
        raise BillingError("non_test_provider_object", False)
    if kind.startswith("invoice."):
        payload = _invoice_fields(data)
        identifier(payload["invoice_code"], "INV_")
        identifier(payload["subscription_code"], "SUB_")
    elif kind == "charge.success":
        payload = {"reference": identifier(data.get("reference"))}
    else:
        payload = {"subscription_code": identifier(data.get("subscription_code"), "SUB_")}
    return _insert_event(hashlib.sha256(raw).hexdigest(), kind, payload)


def initialize_checkout(user):
    existing = db.session.get(BillingAccount, user.id)
    if existing:
        if existing.checkout_url and existing.checkout_status in {"initialized", "failed"}:
            return provider_url(existing.checkout_url, "checkout")
        raise BillingError("checkout_already_exists", False)
    price = SubscriptionPlanPrice.query.filter_by(plan_code="pro", currency="NGN", version=PRICING_VERSION).one_or_none()
    if not price or price.amount_minor != PRO_AMOUNTS_MINOR["NGN"] or price.interval != "month":
        raise BillingError("pricing_not_seeded", False)
    api = provider()
    plan = api.plan()  # Paystack plan overrides initialize amount; verify it first.
    reference = "npd-test-" + secrets.token_hex(24)
    user_id, email = user.id, user.email
    contract = UserSubscription(user_id=user_id, plan_code="pro", status="pending", currency="NGN",
        billing_amount_minor=price.amount_minor, price_version=price.version, provider=PROVIDER)
    db.session.add(contract)
    db.session.flush()
    account = BillingAccount(user_id=user_id, subscription_id=contract.id,
        checkout_reference=reference, plan_reference=plan["plan_code"])
    db.session.add(account)
    try:
        # Unique user_id reserves one checkout before any external mutation.
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise BillingError("checkout_already_exists", False) from None
    try:
        result = api.initialize(email, reference, plan["plan_code"])
        if not isinstance(result, dict) or result.get("reference") != reference:
            raise BillingError("checkout_reference_mismatch", False)
        url = provider_url(result.get("authorization_url"), "checkout")
        updated = db.session.execute(update(BillingAccount).execution_options(synchronize_session=False).where(
            BillingAccount.user_id == user_id, BillingAccount.checkout_status == "initializing").values(
                checkout_url=url, checkout_status="initialized"))
        db.session.commit()
        return url if updated.rowcount else "/account/billing"
    except BillingError:
        db.session.rollback()
        db.session.execute(update(BillingAccount).execution_options(synchronize_session=False).where(
            BillingAccount.user_id == user_id, BillingAccount.checkout_status == "initializing").values(checkout_status="review"))
        db.session.commit()
        # Do not blindly retry initialize after an uncertain network result.
        enqueue_internal("reconcile", {"user_id": user_id}, "initialize-reconcile:" + reference)
        raise


def _transaction(data, account, email, customer_code=None):
    if not isinstance(data, dict) or data.get("domain") != "test":
        raise BillingError("non_test_transaction", False)
    if (data.get("currency") != "NGN" or type(data.get("amount")) is not int
            or data["amount"] != PRO_AMOUNTS_MINOR["NGN"]):
        raise BillingError("transaction_money_mismatch", False)
    identifier(data.get("reference"))
    txn_id = str(data.get("id", ""))
    if not txn_id.isdigit() or not 0 < int(txn_id) < 2**64:
        raise BillingError("transaction_identity_mismatch", False)
    customer = data.get("customer") or {}
    if customer.get("email", "").strip().lower() != email.lower():
        raise BillingError("transaction_customer_mismatch", False)
    code = identifier(customer.get("customer_code"), "CUS_")
    if customer_code and code != customer_code:
        raise BillingError("transaction_customer_mismatch", False)
    if data.get("status") not in {"success", "failed", "abandoned", "reversed"}:
        raise BillingError("transaction_pending")
    paid = timestamp(data.get("paid_at") or data.get("paidAt"), optional=data["status"] != "success")
    if paid and (paid < aware(account.created_at) - timedelta(minutes=5) or paid > utc_now() + timedelta(minutes=5)):
        raise BillingError("transaction_time_mismatch", False)
    return data


def _subscription(data, account, tx):
    test_object(data)
    validate_plan(data.get("plan"), account.plan_reference)
    identifier(data.get("subscription_code"), "SUB_")
    customer = data.get("customer") or {}
    if (customer.get("customer_code") != tx["customer"]["customer_code"]
            or customer.get("email", "").lower() != tx["customer"]["email"].lower()
            or data.get("amount") != PRO_AMOUNTS_MINOR["NGN"]):
        raise BillingError("subscription_customer_mismatch", False)
    if data.get("status") not in {"active", "non-renewing", "attention", "cancelled", "completed", "complete"}:
        raise BillingError("subscription_status_unknown", False)
    timestamp(data.get("updatedAt") or data.get("updated_at"))
    return data


def _first_match(data, tx):
    try:
        created = timestamp(data.get("createdAt") or data.get("created_at"))
        paid = timestamp(tx.get("paid_at") or tx.get("paidAt"))
        # Binding is to the server-created transaction, not an email-only lookup.
        left = (data.get("authorization") or {}).get("authorization_code")
        right = (tx.get("authorization") or {}).get("authorization_code")
        return bool(left and right and hmac.compare_digest(left, right)
                    and abs((created - paid).total_seconds()) <= 600)
    except BillingError:
        return False


def _resolve_account(kind, payload, api):
    user_id = payload.get("user_id")
    if kind in {"reconcile", "command.cancel"} and type(user_id) is int:
        return db.session.get(BillingAccount, user_id)
    reference = payload.get("reference")
    if reference:
        account = BillingAccount.query.filter_by(checkout_reference=reference).one_or_none()
        if account:
            return account
        tx = api.verify(reference)
        if not isinstance(tx, dict) or tx.get("domain") != "test":
            raise BillingError("non_test_transaction", False)
        code = (tx.get("customer") or {}).get("customer_code")
        return BillingAccount.query.join(UserSubscription, UserSubscription.id == BillingAccount.subscription_id).filter(
            UserSubscription.provider == PROVIDER, UserSubscription.provider_customer_reference == code).one_or_none()
    code = payload.get("subscription_code")
    account = BillingAccount.query.join(UserSubscription, UserSubscription.id == BillingAccount.subscription_id).filter(
        UserSubscription.provider == PROVIDER, UserSubscription.provider_subscription_reference == code).one_or_none()
    if account:
        return account
    data = api.subscription(code)
    test_object(data)
    email = (data.get("customer") or {}).get("email", "").lower()
    # Candidate only. _facts verifies the original transaction and authorization before binding.
    return BillingAccount.query.join(User, User.id == BillingAccount.user_id).filter(User.email == email).one_or_none()


def _facts(account, kind, payload, api):
    contract = db.session.get(UserSubscription, account.subscription_id)
    user = db.session.get(User, account.user_id)
    tx = _transaction(api.verify(account.checkout_reference), account, user.email,
                      contract.provider_customer_reference)
    if tx["reference"] != account.checkout_reference:
        raise BillingError("transaction_reference_mismatch", False)
    if tx["status"] != "success":
        return {"initial": tx, "subscription": None, "invoices": [], "cancel": False}
    code = contract.provider_subscription_reference or payload.get("subscription_code")
    if not code:
        customer = tx["customer"]
        plan = api.plan()
        candidates = [item for item in api.subscriptions(customer["id"], plan["id"]) if _first_match(item, tx)]
        if len(candidates) != 1:
            raise BillingError("subscription_not_ready")
        code = candidates[0]["subscription_code"]
    sub = _subscription(api.subscription(code), account, tx)
    if not contract.provider_subscription_reference and not _first_match(sub, tx):
        raise BillingError("subscription_binding_mismatch", False)
    cancelling = kind == "command.cancel"
    if cancelling and sub["status"] in {"active", "attention"}:
        token = sub.get("email_token")
        if not isinstance(token, str) or not token:
            raise BillingError("subscription_token_missing")
        api.cancel(code, token)
        sub = _subscription(api.subscription(code), account, tx)
    invoices = []
    raw_invoices = sub.get("invoices") or []
    if not isinstance(raw_invoices, list):
        raise BillingError("invalid_provider_invoices", False)
    # Bounded recovery; older missing records need the documented event replay workflow.
    dated_invoices = [item for item in raw_invoices if isinstance(item, dict) and item.get("invoice_code")]
    raw_invoices = sorted(dated_invoices, key=lambda item: timestamp(item.get("period_start")), reverse=True)[:5]
    most_recent = sub.get("most_recent_invoice")
    if isinstance(most_recent, dict):
        raw_invoices.append(most_recent)
    if kind.startswith("invoice."):
        event_invoice = dict(payload)
        if kind == "invoice.payment_failed" and event_invoice.get("paid") is not True:
            event_invoice["status"] = "failed"
        raw_invoices.insert(0, event_invoice)
    seen = set()
    raw_invoices.sort(key=lambda item: isinstance(item, dict) and item.get("paid") is True, reverse=True)
    for raw in raw_invoices:
        if not isinstance(raw, dict) or not raw.get("invoice_code"):
            continue
        invoice = dict(raw) if "subscription_code" in raw else _invoice_fields(raw)
        invoice_code = identifier(invoice["invoice_code"], "INV_")
        # The signed event or fetched subscription owns the association.
        if invoice.get("subscription_code") not in (None, code):
            raise BillingError("invoice_subscription_mismatch", False)
        if invoice_code in seen:
            continue
        seen.add(invoice_code)
        start, end = monthly_period(invoice.get("period_start"), invoice.get("period_end"))
        if invoice.get("amount") != PRO_AMOUNTS_MINOR["NGN"]:
            raise BillingError("invoice_money_mismatch", False)
        invoice_tx = None
        if invoice.get("paid") is True:
            transaction = invoice.get("transaction")
            if isinstance(transaction, dict):
                ref = transaction.get("reference")
                transaction_id = transaction.get("id")
            else:
                ref, transaction_id = None, transaction
            if not ref and str(transaction_id).isdigit():
                fetched = api.request("GET", "/transaction/" + str(int(transaction_id)))
                ref = fetched.get("reference")
            if not ref:
                raise BillingError("invoice_transaction_not_ready")
            invoice_tx = _transaction(api.verify(ref), account, user.email, sub["customer"]["customer_code"])
            if invoice_tx["reference"] != ref:
                raise BillingError("transaction_reference_mismatch", False)
            if invoice_tx["status"] != "success":
                raise BillingError("invoice_payment_not_verified")
            paid = timestamp(invoice_tx.get("paid_at") or invoice_tx.get("paidAt"))
            if not start - timedelta(days=1) <= paid < end:
                raise BillingError("invoice_payment_period_mismatch", False)
        invoices.append((invoice, start, end, invoice_tx))
    return {"initial": tx, "subscription": sub, "invoices": invoices, "cancel": cancelling}


def _save_payment(contract, tx, start=None, end=None):
    txn_id, reference = str(tx["id"]), tx["reference"]
    existing = BillingPayment.query.filter(or_(BillingPayment.transaction_id == txn_id,
                                               BillingPayment.reference == reference)).one_or_none()
    if existing and (existing.transaction_id != txn_id or existing.reference != reference
                     or existing.subscription_id != contract.id):
        raise BillingError("payment_binding_conflict", False)
    status = tx["status"] if tx["status"] in {"success", "reversed"} else "failed"
    if not existing:
        existing = BillingPayment(subscription_id=contract.id, transaction_id=txn_id,
            reference=reference, currency="NGN", amount_minor=PRO_AMOUNTS_MINOR["NGN"], status=status)
        db.session.add(existing)
    if existing.status == "reversed" and status != "reversed":
        raise BillingError("reversed_payment_requires_review", False)
    existing.status = status
    existing.paid_at = timestamp(tx.get("paid_at") or tx.get("paidAt"), optional=status != "success")
    existing.verified_at = utc_now()
    if start and end:
        if existing.period_start and (aware(existing.period_start) != start or aware(existing.period_end) != end):
            raise BillingError("payment_period_conflict", False)
        existing.period_start, existing.period_end = start, end
    return existing


def _apply(account, facts):
    contract = db.session.get(UserSubscription, account.subscription_id)
    tx, sub = facts["initial"], facts["subscription"]
    initial = _save_payment(contract, tx)
    if not sub:
        account.checkout_status = "failed" if initial.status == "failed" else "review"
        if initial.status == "reversed":
            contract.status = "past_due"
        account.last_reconciled_at = utc_now()
        return
    code = sub["subscription_code"]
    if contract.provider_subscription_reference not in (None, code):
        raise BillingError("subscription_binding_conflict", False)
    contract.provider_subscription_reference = code
    contract.provider_customer_reference = sub["customer"]["customer_code"]
    account.checkout_status = "verified"
    account.checkout_url = None
    if not initial.period_start:
        # Prefer an invoice's explicit period. Otherwise use the first verified
        # payment and provider's first next-payment date, never now + 30 days.
        period = next(((start, end) for _, start, end, payment in facts["invoices"]
                       if payment and payment["reference"] == tx["reference"]), None)
        if not period:
            paid = timestamp(tx.get("paid_at") or tx.get("paidAt"))
            try:
                period = monthly_period(paid.isoformat(), sub.get("next_payment_date"))
            except BillingError:
                period = None  # Successful charge remains visible but grants no guessed period.
        if period:
            _save_payment(contract, tx, *period)
    for invoice, start, end, payment in facts["invoices"]:
        row = db.session.get(BillingInvoice, invoice["invoice_code"])
        if row and (row.subscription_id != contract.id or aware(row.period_start) != start or aware(row.period_end) != end):
            raise BillingError("invoice_binding_conflict", False)
        if not row:
            row = BillingInvoice(invoice_code=invoice["invoice_code"], subscription_id=contract.id,
                period_start=start, period_end=end, amount_minor=PRO_AMOUNTS_MINOR["NGN"], status="pending")
            db.session.add(row)
        if payment:
            _save_payment(contract, payment, start, end)
            row.status, row.payment_reference = "paid", payment["reference"]
        elif row.status != "paid":
            row.status = "failed" if invoice.get("status") in {"failed", "attention"} else "pending"
        row.observed_at = utc_now()
    provider_updated = timestamp(sub.get("updatedAt") or sub.get("updated_at"))
    if account.provider_updated_at is None or provider_updated >= aware(account.provider_updated_at):
        old_status = account.provider_status
        account.provider_status = sub["status"]
        account.provider_updated_at = provider_updated
        account.next_payment_at = timestamp(sub.get("next_payment_date"), optional=True)
        if facts["cancel"]:
            account.cancel_requested_at = utc_now()
        elif old_status in {"non-renewing", "cancelled"} and sub["status"] == "active":
            account.cancel_requested_at = None
        account.renewal_enabled = sub["status"] in {"active", "attention"} and not account.cancel_requested_at
    db.session.flush()
    now = utc_now()
    paid = BillingPayment.query.filter_by(subscription_id=contract.id, status="success").filter(
        BillingPayment.period_start <= now, BillingPayment.period_end > now).order_by(BillingPayment.period_end.desc()).first()
    latest = paid or BillingPayment.query.filter_by(subscription_id=contract.id, status="success").filter(
        BillingPayment.period_end.is_not(None)).order_by(BillingPayment.period_end.desc()).first()
    if latest:
        contract.current_period_start, contract.current_period_end = latest.period_start, latest.period_end
    if paid:
        contract.status = "active" if account.renewal_enabled else "cancelled"
    elif latest:
        contract.status = "past_due" if account.provider_status == "attention" else "expired"
    else:
        contract.status = "pending"
    account.last_reconciled_at = now


def process_one():
    """Database leases serialize each account across workers and survive process death."""
    if not sandbox_enabled():
        return False
    now, token = utc_now(), secrets.token_hex(24)
    event = BillingEvent.query.filter(BillingEvent.status.in_(("pending", "processing")),
        BillingEvent.available_at <= now).order_by(BillingEvent.received_at).first()
    if not event:
        db.session.rollback()
        return False
    digest = event.digest
    result = db.session.execute(update(BillingEvent).execution_options(synchronize_session=False).where(BillingEvent.digest == digest,
        BillingEvent.status.in_(("pending", "processing")), BillingEvent.available_at <= now).values(
        status="processing", lease_token=token, available_at=now + timedelta(seconds=LEASE_SECONDS),
        attempts=BillingEvent.attempts + 1))
    db.session.commit()
    if not result.rowcount:
        return True
    user_id = None
    try:
        event = db.session.get(BillingEvent, digest)
        api = provider()
        account = _resolve_account(event.event_type, event.payload, api)
        if not account:
            raise BillingError("unmatched_billing_account")
        user_id = account.user_id
        claimed = db.session.execute(update(BillingAccount).execution_options(synchronize_session=False).where(BillingAccount.user_id == user_id,
            or_(BillingAccount.lease_until.is_(None), BillingAccount.lease_until < now)).values(
            lease_token=token, lease_until=now + timedelta(seconds=LEASE_SECONDS)))
        db.session.commit()
        if not claimed.rowcount:
            raise BillingError("account_busy")
        account = db.session.get(BillingAccount, user_id)
        facts = _facts(account, event.event_type, event.payload, api)
        db.session.rollback()
        # Re-acquire the row and verify ownership after all external calls.
        owned = db.session.execute(update(BillingAccount).execution_options(synchronize_session=False).where(BillingAccount.user_id == user_id,
            BillingAccount.lease_token == token, BillingAccount.lease_until > utc_now()).values(lease_token=token))
        if not owned.rowcount:
            raise BillingError("billing_lease_expired")
        account = db.session.get(BillingAccount, user_id)
        _apply(account, facts)
        account.lease_token = account.lease_until = None
        result = db.session.execute(update(BillingEvent).execution_options(synchronize_session=False).where(BillingEvent.digest == digest,
            BillingEvent.lease_token == token).values(status="processed", processed_at=utc_now(),
                                                    lease_token=None, last_error=None))
        if not result.rowcount:
            raise BillingError("event_lease_expired")
        db.session.commit()
        current_app.logger.info("sandbox_billing_event_processed")
    except Exception as exc:
        db.session.rollback()
        code = exc.code if isinstance(exc, BillingError) else "billing_processing_failed"
        retry = not isinstance(exc, BillingError) or exc.retryable
        event = db.session.get(BillingEvent, digest)
        attempts = event.attempts if event else 12
        db.session.execute(update(BillingEvent).execution_options(synchronize_session=False).where(BillingEvent.digest == digest, BillingEvent.lease_token == token).values(
            status="pending" if retry and attempts < 12 else "review", lease_token=None, last_error=code,
            available_at=utc_now() + timedelta(seconds=min(3600, 15 * 2 ** min(attempts, 8)))))
        if user_id:
            db.session.execute(update(BillingAccount).execution_options(synchronize_session=False).where(BillingAccount.user_id == user_id,
                BillingAccount.lease_token == token).values(lease_token=None, lease_until=None))
        db.session.commit()
        current_app.logger.warning("sandbox_billing_event_deferred code=%s error_type=%s", code, type(exc).__name__)
    finally:
        db.session.remove()
    return True


def enqueue_reconciliation():
    now = utc_now()
    cursor = current_app.extensions.get("billing_reconcile_cursor", 0)
    ids = db.session.execute(select(BillingAccount.user_id).where(BillingAccount.user_id > cursor, or_(
        BillingAccount.last_reconciled_at.is_(None),
        BillingAccount.last_reconciled_at < now - timedelta(minutes=15))).order_by(BillingAccount.user_id).limit(100)).scalars().all()
    current_app.extensions["billing_reconcile_cursor"] = ids[-1] if ids else 0
    db.session.rollback()
    bucket = int(now.timestamp()) // 900
    for user_id in ids:
        enqueue_internal("reconcile", {"user_id": user_id}, f"reconcile:{user_id}:{bucket}")
    return len(ids)


def register_billing_commands(app):
    @app.cli.command("billing-worker")
    @click.option("--once", is_flag=True, help="Process at most 100 ready events and exit.")
    def worker(once):
        """Isolated staging worker; never changes the grid-data scheduler."""
        if not sandbox_enabled():
            raise click.ClickException("Sandbox billing is disabled.")
        while True:
            enqueue_reconciliation()
            for _ in range(100):
                if not process_one():
                    break
            if once:
                break
            time.sleep(5)

    @app.cli.command("billing-retry")
    @click.argument("digest")
    def retry(digest):
        """Requeue a reviewed event after correcting its cause, never erase history."""
        if not sandbox_enabled() or len(digest) != 64:
            raise click.ClickException("Sandbox billing disabled or invalid event digest.")
        count = db.session.execute(update(BillingEvent).execution_options(synchronize_session=False).where(BillingEvent.digest == digest,
            BillingEvent.status == "review").values(status="pending", attempts=0, available_at=utc_now(),
                                                   lease_token=None)).rowcount
        db.session.commit()
        click.echo(f"Requeued {count} event(s).")

    @app.cli.command("billing-status")
    def status():
        """Print counts only, never payment/customer identifiers or credentials."""
        from sqlalchemy import func
        for state, count in db.session.execute(select(BillingEvent.status, func.count()).group_by(BillingEvent.status)):
            click.echo(f"{state}: {count}")
