"""SQLAlchemy ORM models — shared Postgres schema with tenant_id + RLS."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from sqlalchemy.orm import Mapped, mapped_column

from controlplane_db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    subdomain: Mapped[str | None] = mapped_column(String(512), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    custom_domain: Mapped[str | None] = mapped_column(String(512), unique=True, nullable=True)
    custom_domain_status: Mapped[str] = mapped_column(
        String(64),
        default="failed",
        server_default=text("'failed'"),
        nullable=False,
    )
    features: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_tenant_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
        Index(
            "uq_users_platform_email",
            "email",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(512), nullable=False)
    gender: Mapped[str] = mapped_column(String(64), nullable=False)
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    sso_provider_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    keycloak_sub: Mapped[str | None] = mapped_column(String(512), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sociacl_attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class UserWalletBinding(Base):
    """One EIP-4361 wallet bound to one Keycloak person.

    Stores the recovered address only. Never a SIWE signature or private key.
    Person-scoped (keycloak_sub), not a second user and not tenant membership.
    """

    __tablename__ = "user_wallet_bindings"
    __table_args__ = (
        Index("uq_user_wallet_bindings_sub", "keycloak_sub", unique=True),
        Index("uq_user_wallet_bindings_address", "wallet_address", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    keycloak_sub: Mapped[str] = mapped_column(String(512), nullable=False)
    email: Mapped[str | None] = mapped_column(String(512), nullable=True)
    wallet_address: Mapped[str] = mapped_column(String(42), nullable=False)
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        Index(
            "uq_roles_tenant_name",
            "tenant_id",
            "name",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
        Index(
            "uq_roles_platform_name",
            "name",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        Index(
            "uq_organizations_tenant_legal_name",
            "tenant_id",
            "legal_name",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    legal_name: Mapped[str] = mapped_column(String(512), nullable=False)


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        Index(
            "uq_groups_tenant_name",
            "tenant_id",
            "name",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )


class UserGroupMembership(Base):
    __tablename__ = "user_group_memberships"
    __table_args__ = (
        Index(
            "uq_user_group_memberships_user_group",
            "user_id",
            "group_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False
    )


class AclCasbinRule(Base):
    """Casbin policy rows; scoped by tenant_id + RLS. Used by acl-service adapter."""

    __tablename__ = "acl_casbin_rules"
    __table_args__ = (Index("ix_acl_casbin_rules_tenant", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    ptype: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v0: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v4: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v5: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __str__(self) -> str:
        arr = [self.ptype or ""]
        for v in (self.v0, self.v1, self.v2, self.v3, self.v4, self.v5):
            if v is None:
                break
            arr.append(v)
        return ", ".join(arr)

    def __repr__(self) -> str:
        return f'<AclCasbinRule {self.id}: "{str(self)}">'


class SociaclShareLink(Base):
    """Opaque share link; token stored as hash only (see sociacl_share_lookup_by_hash)."""

    __tablename__ = "sociacl_share_links"
    __table_args__ = (Index("ix_sociacl_share_links_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    resource_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_descriptor: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    predicate_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uses_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SociaclRecoverySession(Base):
    """Recovery flow metadata only — no secrets (see product sign-off before expanding)."""

    __tablename__ = "sociacl_recovery_sessions"
    __table_args__ = (Index("ix_sociacl_recovery_sessions_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CryptoAgentBudget(Base):
    """Solana-style budget ceiling per owner/mint; allocation tracked in-app (no chain custody here)."""

    __tablename__ = "crypto_agent_budgets"
    __table_args__ = (Index("ix_crypto_agent_budgets_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_pubkey: Mapped[str] = mapped_column(Text, nullable=False)
    mint_pubkey: Mapped[str] = mapped_column(Text, nullable=False)
    ceiling_lamports: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_lamports: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserPasswordReset(Base):
    __tablename__ = "user_password_resets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_secret: Mapped[str] = mapped_column(Text, nullable=False)
    reset_secret_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    preferences: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class StorageSettings(Base):
    __tablename__ = "storage_settings"
    __table_args__ = (
        Index(
            "uq_storage_tenant_provider",
            "tenant_id",
            "provider",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    region: Mapped[str] = mapped_column(String(128), nullable=False)
    aws_access_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    aws_secret_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    aws_bucket_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    azure_connection_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    azure_container_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ChatHistoryAI(Base):
    __tablename__ = "chat_histories_ai"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    histories: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )


class ChatSessionAI(Base):
    __tablename__ = "chat_sessions_ai"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    history_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_histories_ai.id", ondelete="CASCADE"), nullable=False
    )


class UserPasskey(Base):
    __tablename__ = "user_passkeys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    user_email: Mapped[str] = mapped_column(String(512), nullable=False)
    credentials: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )


class UserPasskeyChallenge(Base):
    __tablename__ = "user_passkey_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(512), nullable=False)
    type: Mapped[str] = mapped_column(String(32), default="registration", nullable=False)
    challenge: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserMagicLink(Base):
    __tablename__ = "user_magic_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StripeSettings(Base):
    __tablename__ = "stripe_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    default_currency: Mapped[str] = mapped_column(String(8), default="eur", nullable=False)
    stripe_webhook_secret: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="recurring", nullable=False)
    trial_period_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    stripe_secret_key: Mapped[str | None] = mapped_column(Text, nullable=True)


class BillingRecord(Base):
    __tablename__ = "billing_records"
    __table_args__ = (
        Index("ix_billing_tenant_sub", "tenant_id", "stripe_subscription_id"),
        Index("ix_billing_session", "stripe_session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="pending", nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    plan_level: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_trial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    actor: Mapped[str] = mapped_column(String(32), default="tenant", nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    plan_id: Mapped[str] = mapped_column(String(255), nullable=False)


class NotificationBannerSetting(Base):
    __tablename__ = "notification_banner_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)


class SSOSettings(Base):
    __tablename__ = "sso_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    redirect_uris: Mapped[list | None] = mapped_column(JSONB, nullable=True)


class Branding(Base):
    __tablename__ = "branding_configuration"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_name: Mapped[str] = mapped_column(String(255), default="SaaS Org", nullable=False)
    contact_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    theme_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class MarketplaceListing(Base):
    __tablename__ = "marketplace_listings"
    __table_args__ = (Index("ix_marketplace_listings_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    listing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    price_type: Mapped[str] = mapped_column(String(32), nullable=False)
    price_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    listing_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MarketplaceSellerProfile(Base):
    """Kafka user.created → seller verification (tenant-scoped)."""

    __tablename__ = "marketplace_seller_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_mkt_seller_tenant_user"),
        Index("ix_mkt_seller_profiles_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="verified")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiInferenceRecord(Base):
    """One metered LLM inference row (tenant-scoped via RLS)."""

    __tablename__ = "ai_inference_records"
    __table_args__ = (
        Index("ix_ai_inference_tenant", "tenant_id"),
        Index("ix_ai_inference_user", "tenant_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    billing_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    budget_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crypto_agent_budgets.id", ondelete="SET NULL"),
        nullable=True,
    )


class AiBudgetEventAudit(Base):
    """Append-only mirror of budget.allocated.v1 for observability."""

    __tablename__ = "ai_budget_event_audit"
    __table_args__ = (Index("ix_ai_budget_audit_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crypto_agent_budgets.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    delta_lamports: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ceiling_lamports: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AiAgentEntitlement(Base):
    """Buyer entitlement after purchasing an agent listing (Kafka purchase.completed)."""

    __tablename__ = "ai_agent_entitlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "purchase_id", name="uq_ai_agent_ent_tenant_purchase"),
        Index("ix_ai_agent_ent_buyer", "tenant_id", "buyer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purchase_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("marketplace_purchases.id", ondelete="CASCADE"),
        nullable=False,
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    license_key_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class ApiKey(Base):
    """Tenant-scoped API keys (hashed secret); validated by api-keys-service / gateway."""

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_tenant", "tenant_id"),
        UniqueConstraint("key_prefix", name="uq_api_keys_prefix"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_by_sub: Mapped[str | None] = mapped_column(String(512), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="renter")


class MarketplacePurchase(Base):
    __tablename__ = "marketplace_purchases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    license_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    billing_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("billing_records.id", ondelete="SET NULL"), nullable=True
    )


class HypermeshHardwareClass(Base):
    """Hypermesh hardware class registry (one marketplace tenant)."""

    __tablename__ = "hypermesh_hardware_classes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "class_id", name="uq_hm_hw_class_tenant_id"),
        Index("ix_hm_hw_classes_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False)
    sku: Mapped[str] = mapped_column(String(128), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    public_sku: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    path_b_suite_id: Mapped[str] = mapped_column(String(64), nullable=False)
    hourly_rate_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    advertised_envelope: Mapped[str | None] = mapped_column(Text, nullable=True)


class HypermeshDevice(Base):
    """Hypermesh enrolled box. Secrets are hashes only."""

    __tablename__ = "hypermesh_devices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "serial", name="uq_hm_devices_tenant_serial"),
        Index("ix_hm_devices_tenant", "tenant_id"),
        Index("ix_hm_devices_tenant_site", "tenant_id", "site_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    host_org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    serial: Mapped[str] = mapped_column(String(128), nullable=False)
    path_a: Mapped[dict] = mapped_column(JSONB, nullable=False)
    path_b_state: Mapped[str] = mapped_column(String(32), nullable=False)
    loaded_instance_state: Mapped[str] = mapped_column(String(32), nullable=False)
    loaded_catalog_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enroll_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enroll_token_used_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enroll_token_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    device_secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credential_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    enrolled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_path_b_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_image_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_loaded_model_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_uptime_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_thermal_c: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    usdc_pubkey: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sell_state: Mapped[str] = mapped_column(String(16), nullable=False, default="n/a")
    site_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="host")
    schedule_hold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class HypermeshCatalogEntry(Base):
    """Hypermesh P2 catalog row.

    file_hash is GGUF content sha256 (null until soak stamps it).
    image_digest is the OCI container ref for lease_start (null until pinned).
    """

    __tablename__ = "hypermesh_catalog"
    __table_args__ = (
        UniqueConstraint("tenant_id", "catalog_id", name="uq_hm_catalog_tenant_id"),
        Index("ix_hm_catalog_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    catalog_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_name: Mapped[str] = mapped_column(String(256), nullable=False)
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(256), nullable=True)
    quant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    runtime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    advertised_context: Mapped[int | None] = mapped_column(Integer, nullable=True)
    certified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    per_1k_token_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_hour_min_cents: Mapped[int] = mapped_column(Integer, nullable=False)


class HypermeshLease(Base):
    __tablename__ = "hypermesh_leases"
    __table_args__ = (Index("ix_hm_leases_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    renter_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    host_org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reserved_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    stripe_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    gross_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    loaded_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="renter")


class HypermeshJob(Base):
    __tablename__ = "hypermesh_jobs"
    __table_args__ = (Index("ix_hm_jobs_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    suite_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    image_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    catalog_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(256), nullable=True)
    runtime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ticket: Mapped[str | None] = mapped_column(Text, nullable=True)
    until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sell_state: Mapped[str | None] = mapped_column(String(16), nullable=True)


class HypermeshTunnel(Base):
    """One WireGuard peer per host. The lease is a ticket. Private keys never go to Kafka."""

    __tablename__ = "hypermesh_tunnels"
    __table_args__ = (Index("ix_hm_tunnels_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    lease_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assigned_gateway_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(256), nullable=False)
    server_public_key: Mapped[str] = mapped_column(String(128), nullable=False)
    server_private_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    peer_public_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    peer_private_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    allowed_ips: Mapped[str] = mapped_column(String(64), nullable=False)
    client_address: Mapped[str] = mapped_column(String(64), nullable=False)
    ack_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HypermeshPayout(Base):
    __tablename__ = "hypermesh_payouts"
    __table_args__ = (Index("ix_hm_payouts_tenant", "tenant_id"),)

    lease_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    host_org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    host_pubkey: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    gross_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    stripe_cut_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_take_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    take_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    net_usdc_atoms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class HypermeshGateway(Base):
    """Fyber test-plane gateway. Service secret is hashed; not a host or renter key."""

    __tablename__ = "hypermesh_gateways"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_hm_gateways_tenant_name"),
        Index("ix_hm_gateways_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credential_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="gateway")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HypermeshLeaseAudit(Base):
    """Lease status history a customer can export. No prompts, no keys."""

    __tablename__ = "hypermesh_lease_audit"
    __table_args__ = (
        Index("ix_hm_lease_audit_tenant", "tenant_id"),
        Index("ix_hm_lease_audit_tenant_lease", "tenant_id", "lease_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    lease_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(128), nullable=True)


class HypermeshGatewayMetric(Base):
    """Tunnel/session counters from the Fyber gateway. No prompts, no keys."""

    __tablename__ = "hypermesh_gateway_metrics"
    __table_args__ = (Index("ix_hm_gateway_metrics_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    gateway_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tunnel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    bytes_in: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_out: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    handshake_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HypermeshTicket(Base):
    """Signed #26 lease ticket. The blob is the grant; this is not a WG key."""

    __tablename__ = "hypermesh_tickets"
    __table_args__ = (Index("ix_hm_tickets_tenant", "tenant_id"),)

    lease_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assigned_gateway_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_address: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    exp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ticket: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="renter")


class HypermeshRevokedTicket(Base):
    """Lease ids the router must stop honoring. Does not drop the host WG peer."""

    __tablename__ = "hypermesh_revoked_tickets"
    __table_args__ = (Index("ix_hm_revoked_tickets_tenant", "tenant_id"),)

    lease_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )


class HypermeshAuditorTicket(Base):
    """fyber.auditor.ticket/v0 plane inbox. Site receipt remains actuation SoT."""

    __tablename__ = "hypermesh_auditor_tickets"
    __table_args__ = (
        Index("ix_hm_auditor_tickets_tenant", "tenant_id"),
        Index("ix_hm_auditor_tickets_tenant_site", "tenant_id", "site_id"),
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ticket_schema: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    receipt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    held_call_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    text_redacted: Mapped[str] = mapped_column(String(1000), nullable=False)
    display: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    patch: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes_redacted: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    site_acked_receipt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HypermeshPrivilegeGrant(Base):
    """fyber.privilege_grant/v0 plane store. Docs-first; no schemas/ file."""

    __tablename__ = "hypermesh_privilege_grants"
    __table_args__ = (
        Index("ix_hm_privilege_grants_tenant", "tenant_id"),
        Index("ix_hm_privilege_grants_tenant_site", "tenant_id", "site_id"),
        Index("ix_hm_privilege_grants_tenant_site_status", "tenant_id", "site_id", "status"),
        Index(
            "uq_hm_privilege_grants_natural",
            "tenant_id",
            "site_id",
            "incident_id",
            "trace_id",
            unique=True,
        ),
    )

    grant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[str] = mapped_column(String(128), nullable=False)
    grant_schema: Mapped[str] = mapped_column(String(64), nullable=False)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_by: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason_redacted: Mapped[str] = mapped_column(String(1000), nullable=False)
    asks: Mapped[list] = mapped_column(JSONB, nullable=False)
    rails_profile_requested: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ttl_s_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    blast_radius: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    resolution: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_grant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    integrity: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class HypermeshSiteToken(Base):
    """Panopticon machine/site token. SHA-256 at rest. Scoped to site_id.

    Not hm_gw_, not host device_secret, not a renter portal API key.
    """

    __tablename__ = "hypermesh_site_tokens"
    __table_args__ = (
        UniqueConstraint("secret_hash", name="uq_hm_site_tokens_secret_hash"),
        Index("ix_hm_site_tokens_tenant", "tenant_id"),
        Index("ix_hm_site_tokens_tenant_site", "tenant_id", "site_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    site_id: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_by_sub: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HypermeshHostCertOverride(Base):
    """Host certification / AGX bench validation window. Plane hold + preempt + restore."""

    __tablename__ = "hypermesh_host_cert_overrides"
    __table_args__ = (
        Index("ix_hm_host_cert_overrides_tenant", "tenant_id"),
        Index("ix_hm_host_cert_overrides_tenant_device", "tenant_id", "device_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    preempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    preempted_lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_stop_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cert_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    held_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fail_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
