"""Platform billing persistence; payment decisions stay in the payment owner.

Trusted in-process callers receive transaction-bound handles, never ORM classes
or SQL expressions. Sessions, tenant authority and commit/rollback belong to the
caller. JSON reads are independent copies; assigning a changed copy persists it.
Cross-tenant scans retain the caller's existing RLS privileges.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as _pg_insert
from sqlalchemy.orm import object_session as _object_session

from controlplane_db.models import BillingRecord as _BillingRecord
from controlplane_db.models import FinancialAccountingTotal as _FinancialTotal


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
    def financial_activity_at(self) -> datetime:
        return self._financial_clock("financial_activity_at")

    @property
    def financial_retain_until(self) -> datetime:
        return self._financial_clock("financial_retain_until")

    def _financial_clock(self, column: str) -> datetime:
        # Legacy-mode billing remains mapped to its frozen columns. Only callers
        # explicitly requesting a native financial clock inspect the new schema.
        if column not in {"financial_activity_at", "financial_retain_until"}:
            raise ValueError("Native financial clock unavailable")
        session = _object_session(self._row)
        if session is None:
            raise ValueError("Native financial clock requires the caller transaction")
        available = session.scalar(text("""SELECT count(*)=2 FROM pg_catalog.pg_attribute
            WHERE attrelid=to_regclass('public.billing_records') AND NOT attisdropped
            AND attname IN ('financial_activity_at','financial_retain_until')"""))
        if available is not True:
            raise ValueError("Native financial clock unavailable")
        session.flush()
        value = session.scalar(text(f"""SELECT {column} FROM public.billing_records
            WHERE id=:id AND tenant_id IS NOT DISTINCT FROM :tenant"""),
            {"id": self._row.id, "tenant": self._row.tenant_id})
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Native financial clock unavailable")
        return value

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
            _BillingRecord.extra_metadata["stripe_late_refund"]["operation_id"].astext.is_not(None),
            _BillingRecord.extra_metadata["settle_response"].astext.is_(
                None
            ),
            _BillingRecord.extra_metadata["pending_refund"][
                "stripe_refund_id"
            ].astext.is_not(None),
        ),
        or_(
            _BillingRecord.extra_metadata["stripe_late_refund"]["operation_id"].astext.is_not(None),
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



# Source owners supply validated native figures inside their deletion transaction.
# Fixed metric names prevent identities entering the aggregate dimensions.

class AccountingMetric(StrEnum):
    INVOICE_PAID = "invoice_paid"
    CHARGE_CAPTURED = "charge_captured"
    REFUND_PAID = "refund_paid"
    PROCESSOR_COST = "processor_cost"
    TAX_COLLECTED = "tax_collected"
    TAX_REFUNDED = "tax_refunded"
    HOST_GROSS = "host_gross"
    HOST_NET = "host_net"
    PLATFORM_TAKE = "platform_take"
    HOST_USDC = "host_usdc"
    LEASE_DELIVERED = "lease_delivered"
    PRICING_FILL = "pricing_fill"
    PRICING_TIP = "pricing_tip"


class AccountingUnit(StrEnum):
    MINOR = "minor"
    USDC_ATOM = "usdc_atom"
    USDC_CENT = "usdc_cent"


@dataclass(frozen=True)
class AccountingTotal:
    metric: AccountingMetric
    currency: str
    unit: AccountingUnit
    amount: int


def merge_anonymous_totals(session, totals: Sequence[AccountingTotal]) -> None:
    """Add native source figures; caller owns the transaction and source deletion.

    Currency is the original trusted provider currency code. USD minor units and
    the historical USDC-cent pricing representation are distinct from USDC atoms.
    No party, source record, timestamp or freeform metric is persisted here.
    """
    if len(totals) > 1000:
        raise ValueError("Anonymous accounting batch exceeds limit")
    grouped = {}
    for total in totals:
        if (
            not isinstance(total, AccountingTotal)
            or type(total.metric) is not AccountingMetric
            or type(total.unit) is not AccountingUnit
            or type(total.amount) is not int
            or abs(total.amount) >= 10**78
            or not isinstance(total.currency, str)
            or not (
                (re.fullmatch(r"[A-Z]{3}", total.currency) and total.unit is AccountingUnit.MINOR)
                or (
                    total.currency == "USDC"
                    and total.unit in {AccountingUnit.USDC_ATOM, AccountingUnit.USDC_CENT}
                )
            )
        ):
            raise ValueError("Invalid anonymous accounting total")
        key = (total.metric.value, total.currency, total.unit.value)
        grouped[key] = grouped.get(key, 0) + total.amount
        if abs(grouped[key]) >= 10**78:
            raise ValueError("Anonymous accounting total exceeds precision")
    for (metric, currency, unit), amount in sorted(grouped.items()):
        if not amount:
            continue
        statement = _pg_insert(_FinancialTotal).values(
            metric=metric, currency=currency, unit=unit, amount=amount
        )
        session.execute(statement.on_conflict_do_update(
            index_elements=["metric", "currency", "unit"],
            set_={"amount": _FinancialTotal.amount + statement.excluded.amount},
        ))


def anonymous_accounting_totals(session) -> tuple[AccountingTotal, ...]:
    """Private owner accounting projection with no customer or tenant identifiers."""
    rows = session.scalars(select(_FinancialTotal).order_by(
        _FinancialTotal.metric, _FinancialTotal.currency, _FinancialTotal.unit
    ).execution_options(populate_existing=True))
    return tuple(AccountingTotal(AccountingMetric(row.metric), row.currency,
                                 AccountingUnit(row.unit), int(row.amount)) for row in rows)
