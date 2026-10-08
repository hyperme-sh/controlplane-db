"""Frozen 0053 ORM registry for the mixed Alembic chain only.

Do not use in runtime services. Retire with the old chain in WP-INV-03/13/14.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
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

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


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
        UniqueConstraint("id", "tenant_id", name="uq_organizations_id_tenant"),
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



class HostOrganizationBinding(Base):
    """Default host organization owned by one verified identity in a tenant."""

    __tablename__ = "host_organization_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "tenant_id"],
            ["organizations.id", "organizations.tenant_id"],
            name="fk_host_org_binding_organization_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", name="uq_host_org_binding_organization"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    keycloak_sub: Mapped[str] = mapped_column(String(512), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OrganizationIdpLink(Base):
    """Identity-provider org bound to one enterprise by its owner.

    The external key is an Entra tenant id, a Google hosted domain, or a
    GitHub org login. One key maps to one organization in the tenant.
    """

    __tablename__ = "organization_idp_links"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_key",
            name="uq_org_idp_provider_key",
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
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_key: Mapped[str] = mapped_column(String(256), nullable=False)
    linked_by_sub: Mapped[str] = mapped_column(String(512), nullable=False)


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
    """Recovery flow metadata only — no secrets (see product approval before expanding)."""

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
    """user.created → seller verification (tenant-scoped)."""

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
    __table_args__ = (
        Index("ix_ai_budget_audit_tenant", "tenant_id"),
        Index("uq_ai_budget_event_audit_source_event", "source_event_id", unique=True),
        Index("uq_ai_budget_event_audit_source_key", "source_event_key", unique=True),
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
    source_event_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_event_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AiAgentEntitlement(Base):
    """Buyer entitlement after purchasing an agent listing (purchase.completed)."""

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
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    key_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)


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
        Index("uq_hm_devices_tenant_serial", "tenant_id", "serial", unique=True,
              postgresql_where=text("archived_at IS NULL")),
        Index("uq_hm_devices_tenant_host_name", "tenant_id", "host_name", unique=True,
              postgresql_where=text("archived_at IS NULL AND enrolled AND host_name IS NOT NULL")),
        Index("uq_hm_devices_wg_key", "wg_public_key", unique=True,
              postgresql_where=text("wg_public_key IS NOT NULL")),
        Index("ix_hm_devices_tenant", "tenant_id"),
        Index("ix_hm_devices_tenant_site", "tenant_id", "site_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    host_org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    host_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    host_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="model", server_default=text("'model'")
    )
    schedule_hold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    lab: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    wg_public_key: Mapped[str | None] = mapped_column(String(128), nullable=True)


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
    tokens_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_1k_token_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_hour_min_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, default="seed", server_default=text("'seed'")
    )
    admission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    onboarding_source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)


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
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="renter")
    contract_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ruleset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


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
    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    runtime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ticket: Mapped[str | None] = mapped_column(Text, nullable=True)
    until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sell_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dispatch_skip_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)


class HypermeshTunnel(Base):
    """One WireGuard peer per host. The lease is a ticket. Private keys never go on the event bus."""

    __tablename__ = "hypermesh_tunnels"
    __table_args__ = (Index("ix_hm_tunnels_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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


class HypermeshScorecard(Base):
    """Host scorecard report. decode_tok_s stays null until a timed sample."""

    __tablename__ = "hypermesh_scorecards"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "device_id", "catalog_id", name="uq_hm_scorecard_device_catalog"
        ),
        Index("ix_hm_scorecards_tenant", "tenant_id"),
        Index(
            "uq_hm_scorecard_source",
            "source_repo",
            "source_commit",
            "source_path",
            unique=True,
            postgresql_where=text(
                "source_repo IS NOT NULL AND source_commit IS NOT NULL "
                "AND source_path IS NOT NULL"
            ),
        ),
        Index(
            "uq_hm_scorecard_content",
            "content_sha256",
            unique=True,
            postgresql_where=text("content_sha256 IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    catalog_id: Mapped[str] = mapped_column(String(64), nullable=False)
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    serial: Mapped[str] = mapped_column(String(128), nullable=False)
    image_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    runtime: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_pack: Mapped[str] = mapped_column(String(64), nullable=False)
    image_digest: Mapped[str | None] = mapped_column(String(256), nullable=True)
    host_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_repo: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decode_tok_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    sustained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thermal_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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


class HypermeshDeviceHealth(Base):
    """Latest agent health for one device. Heartbeat is the only writer."""

    __tablename__ = "hypermesh_device_health"
    __table_args__ = (
        CheckConstraint(
            "last_sync_http_status IS NULL OR (last_sync_http_status >= 0 AND last_sync_http_status <= 599)",
            name="ck_hm_health_http_status",
        ),
        CheckConstraint(
            "handshake_age_s IS NULL OR handshake_age_s >= 0",
            name="ck_hm_health_handshake",
        ),
        CheckConstraint(
            "wg_pid IS NULL OR wg_pid >= 0",
            name="ck_hm_health_wg_pid",
        ),
        CheckConstraint(
            "wg_port IS NULL OR (wg_port >= 1 AND wg_port <= 65535)",
            name="ck_hm_health_wg_port",
        ),
        CheckConstraint(
            "lease_container_count IS NULL OR lease_container_count >= 0",
            name="ck_hm_health_containers",
        ),
        CheckConstraint(
            "build_commit IS NULL OR build_commit ~ '^[0-9a-f]{1,64}$'",
            name="ck_hm_health_build_commit",
        ),
        CheckConstraint(
            "disk_free_bytes IS NULL OR disk_free_bytes >= 0",
            name="ck_hm_health_disk_free",
        ),
        CheckConstraint(
            "model_cache_evictable_bytes IS NULL OR model_cache_evictable_bytes >= 0",
            name="ck_hm_health_cache_evictable",
        ),
        Index("ix_hm_device_health_tenant", "tenant_id"),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hypermesh_devices.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    tunnel_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_sync_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    handshake_age_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wg_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wg_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lease_container_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    build_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disk_free_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model_cache_evictable_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sync_error_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class HypermeshFleetAlert(Base):
    """Open or resolved fleet alert. One open row per device and kind."""

    __tablename__ = "hypermesh_fleet_alerts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('heartbeat_stale', 'handshake_stale', 'tunnel_sync_failing', 'build_drift')",
            name="ck_hm_fleet_alert_kind",
        ),
        CheckConstraint(
            "state IN ('open', 'resolved')",
            name="ck_hm_fleet_alert_state",
        ),
        Index("ix_hm_fleet_alerts_tenant", "tenant_id"),
        Index("ix_hm_fleet_alerts_device", "device_id"),
        Index(
            "uq_hm_fleet_alert_open",
            "device_id",
            "kind",
            unique=True,
            postgresql_where=text("state = 'open'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hypermesh_devices.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(256), nullable=True)


class HypermeshFleetHealthConfig(Base):
    """Fleet windows and the deploy-set expected build. Not environment config."""

    __tablename__ = "hypermesh_fleet_health_config"
    __table_args__ = (
        CheckConstraint("heartbeat_stale_s >= 1", name="ck_hm_fleet_cfg_heartbeat"),
        CheckConstraint("handshake_stale_s >= 1", name="ck_hm_fleet_cfg_handshake"),
        CheckConstraint("sync_fail_s >= 1", name="ck_hm_fleet_cfg_sync"),
        CheckConstraint(
            "expected_build_commit IS NULL OR expected_build_commit ~ '^[0-9a-f]{1,64}$'",
            name="ck_hm_fleet_cfg_commit",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    heartbeat_stale_s: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    handshake_stale_s: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    sync_fail_s: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    expected_build_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)


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


class HypermeshPricingPool(Base):
    """One priced supply pool. pool_id is ``<class_id>@<region>``."""

    __tablename__ = "hypermesh_pricing_pools"
    __table_args__ = (
        CheckConstraint("kind IN ('P1', 'P2')", name="ck_hm_pricing_pool_kind"),
        CheckConstraint(
            "pool_id = class_id || '@' || region",
            name="ck_hm_pricing_pool_id_shape",
        ),
        Index("ix_hm_pricing_pools_tenant", "tenant_id"),
    )

    pool_id: Mapped[str] = mapped_column(String(129), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default", server_default=text("'default'")
    )
    kind: Mapped[str] = mapped_column(String(2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HypermeshPricingRound(Base):
    """One realtime or day-ahead clearing. Lottery seed stays null until reveal."""

    __tablename__ = "hypermesh_pricing_rounds"
    __table_args__ = (
        CheckConstraint(
            "round_type IN ('realtime', 'day_ahead')",
            name="ck_hm_pricing_round_type",
        ),
        CheckConstraint(
            "char_length(ruleset_version) > 0",
            name="ck_hm_pricing_round_ruleset",
        ),
        CheckConstraint(
            "char_length(engine_version) > 0",
            name="ck_hm_pricing_round_engine",
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="ck_hm_pricing_round_request_hash",
        ),
        CheckConstraint(
            "lottery_seed_commit ~ '^[0-9a-f]{64}$'",
            name="ck_hm_pricing_round_seed_commit",
        ),
        CheckConstraint(
            "lottery_seed IS NULL OR lottery_seed ~ '^[0-9a-f]{1,128}$'",
            name="ck_hm_pricing_round_seed",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_hm_pricing_round_idempotency"),
        Index("ix_hm_pricing_rounds_tenant", "tenant_id"),
        Index("ix_hm_pricing_rounds_start", "tenant_id", "round_start"),
    )

    round_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    round_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    round_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    lottery_seed_commit: Mapped[str] = mapped_column(String(64), nullable=False)
    lottery_seed: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HypermeshPoolPrice(Base):
    """Clearing result for one pool in one round, plus the state the next round sends."""

    __tablename__ = "hypermesh_pool_prices"
    __table_args__ = (
        CheckConstraint(
            "base_cents >= 0 AND next_base_cents >= 0 AND reserve_cents >= 0 "
            "AND cap_cents >= 0 AND next_ema_cents >= 0 "
            "AND (floor_cents IS NULL OR floor_cents >= 0)",
            name="ck_hm_pool_price_cents",
        ),
        CheckConstraint(
            "char_length(ruleset_version) > 0",
            name="ck_hm_pool_price_ruleset",
        ),
        Index("ix_hm_pool_prices_tenant", "tenant_id"),
    )

    round_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("hypermesh_pricing_rounds.round_id", ondelete="CASCADE"),
        primary_key=True,
    )
    pool_id: Mapped[str] = mapped_column(
        String(129),
        ForeignKey("hypermesh_pricing_pools.pool_id", ondelete="CASCADE"),
        primary_key=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    base_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    next_base_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserve_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    cap_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    utilization: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    demand_hours: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    supply_hours: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    supply_clamped: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reserve_source: Mapped[str] = mapped_column(String(64), nullable=False)
    rationed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    boost_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    boost_multiple: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    at_cap: Mapped[bool] = mapped_column(Boolean, nullable=False)
    at_floor: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scarce: Mapped[bool] = mapped_column(Boolean, nullable=False)
    org_cap_applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    boost: Mapped[dict] = mapped_column(JSONB, nullable=False)
    next_ema_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    trailing_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    supply_tiers: Mapped[list | None] = mapped_column(JSONB, nullable=True)


class HypermeshPricingOrder(Base):
    """Renter order. rungs is the max-price ladder the engine clears against."""

    __tablename__ = "hypermesh_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'filled', 'partial', 'unfilled', 'cancelled')",
            name="ck_hm_pricing_order_status",
        ),
        CheckConstraint("tip_cents >= 0 AND hours > 0", name="ck_hm_pricing_order_money"),
        Index("ix_hm_pricing_orders_tenant", "tenant_id"),
        Index("ix_hm_pricing_orders_org", "tenant_id", "org_id"),
    )

    order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pool_id: Mapped[str] = mapped_column(
        String(129),
        ForeignKey("hypermesh_pricing_pools.pool_id", ondelete="RESTRICT"),
        nullable=False,
    )
    rungs: Mapped[list] = mapped_column(JSONB, nullable=False)
    tip_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hours: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    pain: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    prepay_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HypermeshPricingFill(Base):
    """One awarded slice. pay_cents is per box-hour; total_cents is the slice."""

    __tablename__ = "hypermesh_fills"
    __table_args__ = (
        CheckConstraint(
            "pay_cents >= 0 AND total_cents >= 0 AND tip_cents >= 0 AND hours > 0",
            name="ck_hm_pricing_fill_money",
        ),
        CheckConstraint(
            "char_length(ruleset_version) > 0 AND char_length(engine_version) > 0",
            name="ck_hm_pricing_fill_versions",
        ),
        UniqueConstraint(
            "round_id",
            "order_id",
            "pool_id",
            "rung_index",
            name="uq_hm_pricing_fill_natural",
        ),
        Index("ix_hm_pricing_fills_tenant", "tenant_id"),
        Index("ix_hm_pricing_fills_round", "round_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    round_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("hypermesh_pricing_rounds.round_id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("hypermesh_orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    pool_id: Mapped[str] = mapped_column(
        String(129),
        ForeignKey("hypermesh_pricing_pools.pool_id", ondelete="RESTRICT"),
        nullable=False,
    )
    org_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rung_index: Mapped[int] = mapped_column(Integer, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hypermesh_devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    lease_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hypermesh_leases.id", ondelete="SET NULL"),
        nullable=True,
    )
    pay_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    tip_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    lock_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)


class HypermeshPricingCostInput(Base):
    """Floor inputs for one host device or one class, not both.

    processor_pct, processor_fixed_cents, and expected_hours_per_txn are the
    v0.1.1 token-price fee parameters. They stay null when this row is only a
    power/capex floor.
    """

    __tablename__ = "hypermesh_cost_inputs"
    __table_args__ = (
        CheckConstraint(
            "(device_id IS NOT NULL AND class_id IS NULL) "
            "OR (device_id IS NULL AND class_id IS NOT NULL)",
            name="ck_hm_pricing_cost_scope",
        ),
        CheckConstraint(
            "capex_cents >= 0 AND tariff_cents_per_kwh >= 0 AND loaded_kw >= 0",
            name="ck_hm_pricing_cost_nonneg",
        ),
        CheckConstraint(
            "processor_fixed_cents IS NULL OR processor_fixed_cents >= 0",
            name="ck_hm_pricing_cost_processor",
        ),
        Index("ix_hm_pricing_cost_tenant", "tenant_id"),
        Index("ix_hm_pricing_cost_device", "device_id"),
        Index("ix_hm_pricing_cost_class", "tenant_id", "class_id", "effective_from"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hypermesh_devices.id", ondelete="CASCADE"),
        nullable=True,
    )
    class_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capex_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    loaded_kw: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    tariff_cents_per_kwh: Mapped[int] = mapped_column(Integer, nullable=False)
    overhead: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    residual: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    host_margin: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    processor_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    processor_fixed_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_hours_per_txn: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HypermeshPricingAlert(Base):
    """Open or resolved pricing alert. Pool-level rows leave device_id null.

    Fleet alerts stay on hypermesh_fleet_alerts. That table's device_id is
    NOT NULL, its open unique index is (device_id, kind), and its kind check
    is the four fleet-health conditions. A degraded-round alert is per pool
    and often has no device. Null device_id would not conflict in that
    unique index, so pricing alerts are a separate table.
    """

    __tablename__ = "hypermesh_pricing_alerts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('degraded_rounds', 'engine_unreachable')",
            name="ck_hm_pricing_alert_kind",
        ),
        CheckConstraint(
            "state IN ('open', 'resolved')",
            name="ck_hm_pricing_alert_state",
        ),
        CheckConstraint(
            "pool_id IS NOT NULL OR device_id IS NOT NULL",
            name="ck_hm_pricing_alert_scope",
        ),
        Index("ix_hm_pricing_alerts_tenant", "tenant_id"),
        Index(
            "uq_hm_pricing_alert_open_pool",
            "tenant_id",
            "pool_id",
            "kind",
            unique=True,
            postgresql_where=text(
                "state = 'open' AND pool_id IS NOT NULL AND device_id IS NULL"
            ),
        ),
        Index(
            "uq_hm_pricing_alert_open_device",
            "tenant_id",
            "device_id",
            "kind",
            unique=True,
            postgresql_where=text("state = 'open' AND device_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    pool_id: Mapped[str | None] = mapped_column(
        String(129),
        ForeignKey("hypermesh_pricing_pools.pool_id", ondelete="CASCADE"),
        nullable=True,
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hypermesh_devices.id", ondelete="CASCADE"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(256), nullable=True)


class AiuditorConnection(Base):
    """AIuditor connection row. Hash only. Device secret stays on Hypermesh."""

    __tablename__ = "aiuditor_connections"
    __table_args__ = (
        Index("ix_aiuditor_connections_tenant", "tenant_id"),
        Index("ix_aiuditor_connections_tenant_lease", "tenant_id", "lease_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    credential_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiuditorApproval(Base):
    """AI-use hold. No prompt body. Not fyber.auditor."""

    __tablename__ = "aiuditor_approvals"
    __table_args__ = (Index("ix_aiuditor_approvals_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    who: Mapped[str] = mapped_column(String(256), nullable=False)
    why: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiuditorPolicy(Base):
    """Org allow/hold/deny. No prompt body."""

    __tablename__ = "aiuditor_policies"
    __table_args__ = (Index("ix_aiuditor_policies_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    disposition: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiuditorContract(Base):
    """Spine §D grant. Not a handoff package. Not a chain SoT."""

    __tablename__ = "aiuditor_contracts"
    __table_args__ = (
        Index("ix_aiuditor_contracts_tenant", "tenant_id"),
        Index("ix_aiuditor_contracts_tenant_lease", "tenant_id", "lease_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    parties: Mapped[list] = mapped_column(JSONB, nullable=False)
    meters: Mapped[list] = mapped_column(JSONB, nullable=False)
    rail: Mapped[str] = mapped_column(String(32), nullable=False)
    until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dispute_tip: Mapped[str | None] = mapped_column(String(120), nullable=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    signed_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiuditorViolation(Base):
    """Violation on a signed Contract. Dispute reads cert + audit."""

    __tablename__ = "aiuditor_violations"
    __table_args__ = (
        Index("ix_aiuditor_violations_tenant", "tenant_id"),
        Index("ix_aiuditor_violations_tenant_contract", "tenant_id", "contract_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiuditorCatalog(Base):
    """AIuditor catalog row. Not a Hypermesh class or catalog. Not TURN."""

    __tablename__ = "aiuditor_catalog"
    __table_args__ = (Index("ix_aiuditor_catalog_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    backend: Mapped[str] = mapped_column(String(32), nullable=False)
    class_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    catalog_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    meters: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiuditorEnvelope(Base):
    """Lab class envelope. One artifact per class_id. Not a Hypermesh scorecard."""

    __tablename__ = "aiuditor_envelopes"
    __table_args__ = (
        Index("ix_aiuditor_envelopes_tenant", "tenant_id"),
        Index("ix_aiuditor_envelopes_tenant_class", "tenant_id", "class_id"),
        UniqueConstraint(
            "tenant_id",
            "class_id",
            "catalog_id",
            name="uq_aiuditor_envelope_class_catalog",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_id: Mapped[str] = mapped_column(String(64), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    quant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    runtime: Mapped[str] = mapped_column(String(64), nullable=False)
    context: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    decode_tok_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    thermal_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiuditorSuiteMember(Base):
    """Core cert suite membership. Compact-cert jobs read this list."""

    __tablename__ = "aiuditor_suite_members"
    __table_args__ = (
        Index("ix_aiuditor_suite_members_tenant", "tenant_id"),
        Index("ix_aiuditor_suite_members_tenant_class", "tenant_id", "class_id"),
        UniqueConstraint(
            "tenant_id",
            "class_id",
            "catalog_id",
            name="uq_aiuditor_suite_class_catalog",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiuditorAdmission(Base):
    """Uploaded-model admission. Quarantine/sandbox stubs stay pending."""

    __tablename__ = "aiuditor_admissions"
    __table_args__ = (
        Index("ix_aiuditor_admissions_tenant", "tenant_id"),
        Index("ix_aiuditor_admissions_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    file_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    quant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    license: Mapped[str] = mapped_column(String(64), nullable=False)
    intended_class: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sandbox_soak_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sandbox_egress_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sandbox_egress_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiuditorCandidate(Base):
    """Daily crawl metadata pin. Weights never stored here."""

    __tablename__ = "aiuditor_candidates"
    __table_args__ = (
        Index("ix_aiuditor_candidates_tenant", "tenant_id"),
        Index("ix_aiuditor_candidates_tenant_class", "tenant_id", "class_id"),
        Index("ix_aiuditor_candidates_tenant_status", "tenant_id", "status"),
        UniqueConstraint(
            "tenant_id",
            "repo",
            "revision",
            "file_name",
            "class_id",
            name="uq_aiuditor_candidate_source_class",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    repo: Mapped[str] = mapped_column(String(256), nullable=False)
    revision: Mapped[str] = mapped_column(String(128), nullable=False)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    license: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quant: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    publisher: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_id: Mapped[str] = mapped_column(String(64), nullable=False)
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    soak_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OperatorBan(Base):
    """Durable ban. Soft-delete, sell pause, and cert suspend are other nouns."""

    __tablename__ = "operator_bans"
    __table_args__ = (
        Index("ix_operator_bans_tenant", "tenant_id"),
        Index(
            "uq_operator_bans_active",
            "tenant_id",
            "subject_kind",
            "subject_id",
            unique=True,
            postgresql_where=text("lifted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    subject_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lifted_by: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lift_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_label: Mapped[str | None] = mapped_column(String(512), nullable=True)


class OperatorAudit(Base):
    """Append-only operator reason log. No passwords, links, or mail secrets."""

    __tablename__ = "operator_audit"
    __table_args__ = (Index("ix_operator_audit_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(512), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OperatorPeer(Base):
    """Another Panopticon recorded on this plane. Not a chain store."""

    __tablename__ = "operator_peers"
    __table_args__ = (Index("ix_operator_peers_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    peer_tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_health_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_health_detail: Mapped[str] = mapped_column(String(500), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OperatorMailQuota(Base):
    """Account-wide Mailgun month counter. Not tenant scoped. Limit is 10000."""

    __tablename__ = "operator_mail_quota"

    year_month: Mapped[str] = mapped_column(String(7), primary_key=True)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class HypermeshHostRegistration(Base):
    """Immutable installation request; only hashes of locally held credentials."""

    __tablename__ = "hypermesh_host_registrations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["host_org_id", "tenant_id"], ["organizations.id", "organizations.tenant_id"],
            name="fk_hm_registration_org_tenant", ondelete="CASCADE",
        ),
        CheckConstraint("state IN ('pending', 'approved', 'denied', 'completed')",
                        name="ck_hm_registration_state"),
        Index("ix_hm_registration_owner", "tenant_id", "owner_sub"),
        Index("ix_hm_registration_outbox", "tenant_id", "created_at", "id",
              postgresql_where=text("enrollment_event IS NOT NULL AND event_forwarded_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    owner_sub: Mapped[str] = mapped_column(String(512), nullable=False)
    host_org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request: Mapped[dict] = mapped_column(JSONB, nullable=False)
    enrollment_event: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    event_forwarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hypermesh_devices.id"), nullable=True, unique=True
    )



class HypermeshOnboardingRun(Base):
    """Frozen workload authority and one immutable result per owner installation."""
    __tablename__ = "hypermesh_onboarding_runs"
    __table_args__ = (
        Index("ix_hm_onboarding_device", "tenant_id", "device_id"),
        CheckConstraint("state IN ('planned', 'passed', 'failed')", name="ck_hm_onboarding_state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hypermesh_devices.id"), nullable=False)
    registration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hypermesh_host_registrations.id"), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(512), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
