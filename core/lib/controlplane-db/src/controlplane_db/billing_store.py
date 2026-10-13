"""Platform billing persistence; payment decisions stay in the payment owner.

Trusted in-process callers receive transaction-bound handles, never ORM classes
or SQL expressions. Sessions, tenant authority and commit/rollback belong to the
caller. JSON reads are independent copies; assigning a changed copy persists it.
Cross-tenant scans retain the caller's existing RLS privileges.
"""
from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime
from sqlalchemy import select, func, or_, text
from controlplane_db.models import BillingRecord as _BillingRecord


class BillingPayment:
    """Billing values backed by the caller's transaction; no ORM query surface."""
    __slots__ = ("_row",)

    def __init__(self, **values):
        self._row = _BillingRecord(**deepcopy(values))

    @property
    def id(self) -> uuid.UUID:
        return self._row.id

    @property
    def tenant_id(self) -> uuid.UUID | None:
        return self._row.tenant_id

    @property
    def created_at(self) -> datetime:
        return self._row.created_at

    @property
    def updated_at(self) -> datetime:
        return self._row.updated_at

    @property
    def scope(self) -> str:
        return self._row.scope

    @scope.setter
    def scope(self, value: str) -> None:
        self._row.scope = value

    @property
    def actor(self) -> str:
        return self._row.actor

    @actor.setter
    def actor(self, value: str) -> None:
        self._row.actor = value

    @property
    def user_id(self) -> uuid.UUID | None:
        return self._row.user_id

    @user_id.setter
    def user_id(self, value: uuid.UUID | None) -> None:
        self._row.user_id = value

    @property
    def payment_type(self) -> str:
        return self._row.payment_type

    @payment_type.setter
    def payment_type(self, value: str) -> None:
        self._row.payment_type = value

    @property
    def currency(self) -> str:
        return self._row.currency

    @currency.setter
    def currency(self, value: str) -> None:
        self._row.currency = value

    @property
    def amount(self) -> int | None:
        return self._row.amount

    @amount.setter
    def amount(self, value: int | None) -> None:
        self._row.amount = value

    @property
    def stripe_customer_id(self) -> str | None:
        return self._row.stripe_customer_id

    @stripe_customer_id.setter
    def stripe_customer_id(self, value: str | None) -> None:
        self._row.stripe_customer_id = value

    @property
    def stripe_subscription_id(self) -> str | None:
        return self._row.stripe_subscription_id

    @stripe_subscription_id.setter
    def stripe_subscription_id(self, value: str | None) -> None:
        self._row.stripe_subscription_id = value

    @property
    def stripe_session_id(self) -> str | None:
        return self._row.stripe_session_id

    @stripe_session_id.setter
    def stripe_session_id(self, value: str | None) -> None:
        self._row.stripe_session_id = value

    @property
    def product_id(self) -> str | None:
        return self._row.product_id

    @product_id.setter
    def product_id(self, value: str | None) -> None:
        self._row.product_id = value

    @property
    def price_id(self) -> str | None:
        return self._row.price_id

    @price_id.setter
    def price_id(self, value: str | None) -> None:
        self._row.price_id = value

    @property
    def status(self) -> str:
        return self._row.status

    @status.setter
    def status(self, value: str) -> None:
        self._row.status = value

    @property
    def current_period_end(self) -> datetime | None:
        return self._row.current_period_end

    @current_period_end.setter
    def current_period_end(self, value: datetime | None) -> None:
        self._row.current_period_end = value

    @property
    def canceled_at(self) -> datetime | None:
        return self._row.canceled_at

    @canceled_at.setter
    def canceled_at(self, value: datetime | None) -> None:
        self._row.canceled_at = value

    @property
    def cancellation_reason(self) -> str | None:
        return self._row.cancellation_reason

    @cancellation_reason.setter
    def cancellation_reason(self, value: str | None) -> None:
        self._row.cancellation_reason = value

    @property
    def extra_metadata(self) -> dict:
        return deepcopy(self._row.extra_metadata)

    @extra_metadata.setter
    def extra_metadata(self, value: dict) -> None:
        self._row.extra_metadata = deepcopy(value)


def _view(row):
    if row is None or not isinstance(row, _BillingRecord):
        return row
    view = object.__new__(BillingPayment)
    view._row = row
    return view


def add_payment(session, payment: BillingPayment) -> None:
    session.add(payment._row)


def refresh_payment(session, payment: BillingPayment) -> None:
    session.refresh(payment._row)


def detach_payment(session, payment: BillingPayment) -> None:
    session.expunge(payment._row)


def get_payment(session, tenant_id: uuid.UUID, billing_id: uuid.UUID, *,
                lock: bool = False, skip_locked: bool = False,
                refresh: bool = False) -> BillingPayment | None:
    stmt = select(_BillingRecord).where(_BillingRecord.id == billing_id,
                                      _BillingRecord.tenant_id == tenant_id)
    if lock:
        stmt = stmt.with_for_update(skip_locked=skip_locked)
    if refresh:
        stmt = stmt.execution_options(populate_existing=True)
    return _view(session.scalar(stmt))


def list_payments(session, tenant_id: uuid.UUID, *, limit: int = 50,
                  offset: int = 0) -> tuple[list[BillingPayment], int]:
    stmt = select(_BillingRecord).where(_BillingRecord.tenant_id == tenant_id)
    total = int(session.scalar(select(func.count()).select_from(_BillingRecord)
                .where(_BillingRecord.tenant_id == tenant_id)) or 0)
    rows = session.scalars(stmt.order_by(_BillingRecord.created_at.desc())
                            .limit(limit).offset(offset)).all()
    return [_view(row) for row in rows], total


def find_metadata_payment(session, tenant_id: uuid.UUID, key: str,
                          value: str) -> BillingPayment | None:
    if key not in {"invoice_id", "usage_identifier"}:
        raise ValueError("Unsupported billing lookup")
    stmt = select(_BillingRecord).where(_BillingRecord.tenant_id == tenant_id,
        _BillingRecord.extra_metadata[key].astext == value).limit(1)
    return _view(session.scalars(stmt).first())


def find_subscription_payment(session, tenant_id: uuid.UUID,
                              subscription_id: str) -> BillingPayment | None:
    stmt = select(_BillingRecord).where(_BillingRecord.tenant_id == tenant_id,
        _BillingRecord.stripe_subscription_id == subscription_id)
    return _view(session.scalars(stmt.order_by(_BillingRecord.created_at.asc())).first())


def subscription_tenant(session, subscription_id: str) -> uuid.UUID | None:
    """Cross-tenant webhook discovery, subject to caller RLS authority."""
    return session.scalar(select(_BillingRecord.tenant_id).where(
        _BillingRecord.stripe_subscription_id == subscription_id,
        _BillingRecord.tenant_id.is_not(None)).order_by(_BillingRecord.created_at.asc()).limit(1))


def host_transfer_payments(session, tenant_id: uuid.UUID, org_id: uuid.UUID, *,
                           limit: int = 100, offset: int = 0,
                           billing_id: uuid.UUID | None = None) -> list[BillingPayment]:
    stmt = select(_BillingRecord).where(_BillingRecord.tenant_id == tenant_id,
        _BillingRecord.extra_metadata["stripe_connect_transfer"]["host_org_id"].astext == str(org_id))
    if billing_id is not None:
        stmt = stmt.where(_BillingRecord.id == billing_id)
    rows = session.scalars(stmt.order_by(_BillingRecord.id).limit(limit).offset(offset)).all()
    return [_view(row) for row in rows]


def unfinished_side_effect_claims(session) -> list[tuple]:
    """Preserve the role-gated cross-tenant scan; caller interprets staleness."""
    return list(session.execute(text("""
        SELECT id, tenant_id, metadata->>'side_effects_claimed_at' AS claimed_at
        FROM billing_records
        WHERE metadata->'settle_side_effects' IS NOT NULL
          AND COALESCE(metadata->>'side_effects_done', 'false') <> 'true'
    """)).all())

def transfer_scan_page(session, *, after: uuid.UUID | None = None) -> list[tuple]:
    """Ordered cross-tenant scan under caller RLS; mutations re-lock by tenant."""
    cursor = after
    query = select(_BillingRecord.tenant_id, _BillingRecord.id).where(
        _BillingRecord.extra_metadata["payment_rail"].astext
        == "stripe_stablecoin",
        _BillingRecord.extra_metadata["connect_transfer_enabled"].astext
        == "true",
        or_(
            _BillingRecord.extra_metadata['stripe_connect_transfer']["status"].astext.is_(None),
            _BillingRecord.extra_metadata['stripe_connect_transfer']["status"].astext.in_(
                [
                    "prepared",
                    "dispatching",
                    "waiting_recipient",
                    "retry",
                    "reversing",
                ]
            ),
            _BillingRecord.extra_metadata['stripe_connect_reversal_pending'].astext == "true",
        ),
        _BillingRecord.scope == "lease",
        _BillingRecord.status.in_(["succeeded", "refunded"]),
    )
    if cursor:
        query = query.where(_BillingRecord.id > cursor)
    return list(session.execute(query.order_by(_BillingRecord.id).limit(100)).all())

def refund_scan_page(session, *, after: uuid.UUID | None = None) -> list[tuple]:
    """Ordered cross-tenant scan under caller RLS; mutations re-lock by tenant."""
    cursor = after
    query = select(_BillingRecord.tenant_id, _BillingRecord.id).where(
        _BillingRecord.scope == "lease",
        _BillingRecord.extra_metadata["payment_rail"].astext
        == "stripe_stablecoin",
        or_(
            _BillingRecord.extra_metadata["settle_response"].astext.is_(
                None
            ),
            _BillingRecord.extra_metadata["pending_refund"][
                "stripe_refund_id"
            ].astext.is_not(None),
        ),
        or_(
            _BillingRecord.status == "refund_required",
            _BillingRecord.extra_metadata["pending_refund"].astext.is_not(
                None
            ),
        ),
        or_(
            _BillingRecord.extra_metadata['stripe_refund_recovery']["status"].astext.is_(None),
            _BillingRecord.extra_metadata['stripe_refund_recovery']["status"].astext.in_(
                ["retry", "succeeded"]
            ),
            _BillingRecord.extra_metadata['stripe_refund_recovery']["reason"].astext
            == "payer_mismatch_controls_required",
        ),
    )
    if cursor:
        query = query.where(_BillingRecord.id > cursor)
    return list(session.execute(query.order_by(_BillingRecord.id).limit(100)).all())

def mismatch_fee_scan_page(session, *, after: uuid.UUID | None = None) -> list[tuple]:
    """Ordered cross-tenant scan under caller RLS; mutations re-lock by tenant."""
    cursor = after
    query = select(_BillingRecord.tenant_id, _BillingRecord.id).where(
        _BillingRecord.scope == "lease",
        _BillingRecord.status.in_(["refund_required", "refunded"]),
        _BillingRecord.extra_metadata["payment_rail"].astext
        == "stripe_stablecoin",
        _BillingRecord.extra_metadata["stripe_payer_mismatch"].astext.is_not(
            None
        ),
    )
    if cursor:
        query = query.where(_BillingRecord.id > cursor)
    return list(session.execute(query.order_by(_BillingRecord.id).limit(100)).all())

