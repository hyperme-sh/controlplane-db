"""Platform-owned payment identity and Stripe credential projections.

Read-only owner contract for trusted server callers. Every person/credential
lookup explicitly binds the tenant even when the connection bypasses RLS.
Webhook-secret enumeration keeps the caller's existing database privileges;
it never changes roles or widens RLS scope. Never log returned credentials.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from controlplane_db.models import ApiKey, StripeSettings, User


class UnstablePayerIdentity(ValueError):
    """The platform cannot resolve a key or user to one stable payer subject."""


@dataclass(frozen=True)
class StripeCredentials:
    """Detached tenant credential projection; secrets are excluded from repr."""

    tenant_id: uuid.UUID
    stripe_secret_key: str | None = field(repr=False)


def _uuid_from_sub(sub: str | None) -> uuid.UUID | None:
    raw = str(sub or "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _set_guc(session: Session, tenant_id: uuid.UUID) -> None:
    session.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


def user_id_for_sub(
    sync_engine,
    tenant_id: uuid.UUID,
    sub: str | None,
) -> uuid.UUID | None:
    """Return users.id when ``sub`` is that id or ``keycloak_sub`` for this tenant."""

    raw = str(sub or "").strip()
    if not raw:
        return None
    with Session(sync_engine) as session:
        _set_guc(session, tenant_id)
        as_uuid = _uuid_from_sub(raw)
        if as_uuid is not None:
            row = session.scalars(
                select(User).where(User.id == as_uuid, User.tenant_id == tenant_id)
            ).first()
            if row is not None:
                return row.id
        row = session.scalars(
            select(User).where(
                User.keycloak_sub == raw,
                User.tenant_id == tenant_id,
            )
        ).first()
        if row is not None:
            return row.id
    return None


def service_user_id_for_apikey_sub(
    sync_engine,
    tenant_id: uuid.UUID,
    sub: str | None,
) -> uuid.UUID | None:
    """Recorded service→user map: api_keys.created_by_sub for ``apikey:{id}``."""

    raw = str(sub or "").strip()
    if not raw.startswith("apikey:"):
        return None
    try:
        key_id = uuid.UUID(raw.split(":", 1)[1])
    except (ValueError, IndexError):
        return None
    with Session(sync_engine) as session:
        _set_guc(session, tenant_id)
        key = session.scalars(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.tenant_id == tenant_id,
            )
        ).first()
        if key is None or not key.created_by_sub:
            return None
    return user_id_for_sub(sync_engine, tenant_id, key.created_by_sub)


def mismatch_person_sub(
    sync_engine, tenant_id: uuid.UUID, actor_sub: str
) -> str:
    """Resolve tenant-user and key subjects to one stable person, never a client ID."""
    from sqlalchemy import or_

    if not actor_sub.startswith("apikey:"):
        local_id = _uuid_from_sub(actor_sub)
        if local_id is None:
            return actor_sub
        with Session(sync_engine) as session:
            _set_guc(session, tenant_id)
            members = session.scalars(
                select(User).where(
                    User.tenant_id == tenant_id,
                    or_(User.id == local_id, User.keycloak_sub == actor_sub),
                )
            ).all()
            # UUID-shaped OIDC subjects need not have a local membership row yet.
            if not members:
                return actor_sub
            subjects = {
                member.keycloak_sub for member in members if member.keycloak_sub
            }
            if (
                len(subjects) != 1
                or any(not member.keycloak_sub for member in members)
                or next(iter(subjects)).startswith("apikey:")
            ):
                raise UnstablePayerIdentity("User has no stable payer identity")
            return subjects.pop()

    try:
        key_id = uuid.UUID(actor_sub.split(":", 1)[1])
    except ValueError:
        raise UnstablePayerIdentity("API key has no stable payer identity") from None
    with Session(sync_engine) as session:
        _set_guc(session, tenant_id)
        key = session.scalars(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.tenant_id == tenant_id,
            )
        ).first()
        marker = key.created_by_sub if key else None
        if not marker or "@" in marker:
            raise UnstablePayerIdentity("API key has no stable payer identity")
        creator = session.scalars(
            select(User).where(
                User.tenant_id == tenant_id,
                or_(
                    User.keycloak_sub == marker,
                    User.id == _uuid_from_sub(marker),
                )
                if _uuid_from_sub(marker)
                else User.keycloak_sub == marker,
            )
        ).all()
        subjects = {user.keycloak_sub for user in creator if user.keycloak_sub}
        if len(subjects) != 1 or any(not user.keycloak_sub for user in creator):
            raise UnstablePayerIdentity("API key has no stable payer identity")
        subject = subjects.pop()
        if subject.startswith("apikey:"):
            raise UnstablePayerIdentity("API key has no stable payer identity")
        return subject


def get_stripe_settings(
    sync_engine, tenant_id: uuid.UUID
) -> StripeCredentials | None:
    with Session(sync_engine) as session:
        _set_guc(session, tenant_id)
        row = session.scalars(
            select(StripeSettings).where(StripeSettings.tenant_id == tenant_id)
        ).first()
        if row is None:
            return None
        return StripeCredentials(
            tenant_id=tenant_id, stripe_secret_key=row.stripe_secret_key
        )


def iter_webhook_secrets(sync_engine) -> list[tuple[uuid.UUID | None, str]]:
    """Load all (tenant_id, webhook_secret) pairs for signature verification (superuser path)."""
    with Session(sync_engine) as session:
        rows = session.execute(
            text(
                "SELECT tenant_id, stripe_webhook_secret FROM stripe_settings "
                "WHERE stripe_webhook_secret IS NOT NULL AND stripe_webhook_secret <> ''"
            )
        ).all()
        return [(r[0], r[1]) for r in rows]
