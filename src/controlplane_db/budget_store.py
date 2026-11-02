"""Platform-owned agent-budget commands and immutable projections.

No chain custody or provider I/O. Scoped commands filter tenant explicitly;
legacy burns participate in the caller's transaction and never commit it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from controlplane_db.models import CryptoAgentBudget, User


@dataclass(frozen=True)
class AgentBudget:
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    label: str | None
    owner_pubkey: str
    mint_pubkey: str
    ceiling_lamports: int
    allocated_lamports: int
    created_at: datetime
    updated_at: datetime


def _view(row: CryptoAgentBudget) -> AgentBudget:
    return AgentBudget(
        id=row.id, tenant_id=row.tenant_id, user_id=row.user_id, label=row.label,
        owner_pubkey=row.owner_pubkey, mint_pubkey=row.mint_pubkey,
        ceiling_lamports=row.ceiling_lamports, allocated_lamports=row.allocated_lamports,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _set_guc(session: Session, tenant_id: uuid.UUID) -> None:
    session.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


def user_exists_for_tenant(
    sync_engine, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Only link budgets to users that exist for this tenant (FK + product semantics)."""
    with Session(sync_engine) as session:
        _set_guc(session, tenant_id)
        row = session.scalars(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id)
        ).first()
        return row is not None


def create_budget(
    sync_engine,
    tenant_id: uuid.UUID,
    *,
    owner_pubkey: str,
    mint_pubkey: str,
    ceiling_lamports: int,
    label: str | None,
    user_id: uuid.UUID | None,
) -> AgentBudget:
    row = CryptoAgentBudget(
        tenant_id=tenant_id,
        user_id=user_id,
        label=label,
        owner_pubkey=owner_pubkey,
        mint_pubkey=mint_pubkey,
        ceiling_lamports=ceiling_lamports,
        allocated_lamports=0,
    )
    with Session(sync_engine) as session:
        _set_guc(session, tenant_id)
        if user_id is not None and not session.scalar(
            select(User.id).where(User.id == user_id, User.tenant_id == tenant_id)
        ):
            raise ValueError("Budget user must belong to the requested tenant")
        session.add(row)
        session.flush()
        result = _view(row)
        session.commit()
        return result


def list_budgets_for_tenant(
    sync_engine,
    tenant_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentBudget], int]:
    with Session(sync_engine) as session:
        _set_guc(session, tenant_id)
        base = select(CryptoAgentBudget).where(CryptoAgentBudget.tenant_id == tenant_id)
        total = session.scalar(
            select(func.count()).select_from(CryptoAgentBudget).where(
                CryptoAgentBudget.tenant_id == tenant_id
            )
        )
        total = int(total or 0)
        rows = session.scalars(
            base.order_by(CryptoAgentBudget.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return [_view(row) for row in rows], int(total)


def get_budget(
    sync_engine, tenant_id: uuid.UUID, budget_id: uuid.UUID
) -> AgentBudget | None:
    """Tenant-scoped lookup (explicit filter; superuser connections bypass RLS)."""
    with Session(sync_engine) as session:
        _set_guc(session, tenant_id)
        row = session.scalars(
            select(CryptoAgentBudget).where(
                CryptoAgentBudget.id == budget_id,
                CryptoAgentBudget.tenant_id == tenant_id,
            )
        ).first()
        return _view(row) if row is not None else None


def try_allocate(
    sync_engine, tenant_id: uuid.UUID, budget_id: uuid.UUID, delta: int
) -> AgentBudget | None:
    """Return updated row if allocation fits ceiling; None if not enough headroom."""
    if delta <= 0:
        return None
    with Session(sync_engine) as session:
        _set_guc(session, tenant_id)
        obj = session.scalars(
            select(CryptoAgentBudget).where(
                CryptoAgentBudget.id == budget_id,
                CryptoAgentBudget.tenant_id == tenant_id,
            ).with_for_update()
        ).first()
        if obj is None:
            return None
        if obj.allocated_lamports + delta > obj.ceiling_lamports:
            return None
        obj.allocated_lamports += delta
        session.flush()
        result = _view(obj)
        session.commit()
        return result


def burn_legacy_budget_allocation(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    budget_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    atoms: int,
) -> None:
    """Burn a retained legacy allocation in the caller's billing transaction.

    Caller locks its billing row first. This command then locks the tenant's
    budget, mutates only allocation and flushes. It never commits, rolls back,
    closes the caller session or credits a wallet. The billing owner supplies
    the idempotency guard; replay without that guard is not idempotent.
    """
    if atoms <= 0:
        return
    _set_guc(session, tenant_id)
    row = None
    if budget_id is not None:
        row = session.scalar(
            select(CryptoAgentBudget).where(
                CryptoAgentBudget.id == budget_id,
                CryptoAgentBudget.tenant_id == tenant_id,
            ).with_for_update().execution_options(populate_existing=True)
        )
    if row is None and user_id is not None:
        row = session.scalar(
            select(CryptoAgentBudget).where(
                CryptoAgentBudget.tenant_id == tenant_id,
                CryptoAgentBudget.user_id == user_id,
                CryptoAgentBudget.label == "fake-usdc",
            ).with_for_update().execution_options(populate_existing=True)
        )
    if row is not None:
        row.allocated_lamports = max(0, int(row.allocated_lamports) - atoms)
        session.flush()
