import json
import hashlib
from typing import Optional
from sqlalchemy import String, Text, select, event
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

GENESIS_HASH = "0" * 64


def compute_audit_hash(
    previous_hash: Optional[str],
    id: str,
    timestamp: str,
    actor: str,
    actor_type: str,
    action: str,
    resource: str,
    resource_id: Optional[str],
    status: str,
    module: str,
    ip_address: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata_json: Optional[str] = None,
) -> str:
    """Computes deterministic SHA-256 digest of canonical audit log representation."""
    canonical_dict = {
        "previous_hash": previous_hash or GENESIS_HASH,
        "id": str(id or ""),
        "timestamp": str(timestamp or ""),
        "actor": str(actor or ""),
        "actor_type": str(actor_type or "user"),
        "action": str(action or ""),
        "resource": str(resource or ""),
        "resource_id": str(resource_id or ""),
        "status": str(status or "success"),
        "module": str(module or "system"),
        "ip_address": str(ip_address or ""),
        "session_id": str(session_id or ""),
        "metadata_json": str(metadata_json or ""),
    }
    canonical_bytes = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    timestamp: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False, default="user") # user, system, ai, donor
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource: Mapped[str] = mapped_column(String(150), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
    authorization: Mapped[str] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="success") # success, failed, pending
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # blood, organ, ambulance, system, auth
    ip_address: Mapped[str] = mapped_column(String(50), nullable=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)
    previous_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    record_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)


@event.listens_for(AuditLog, "before_insert")
def populate_audit_hash(mapper, connection, target: AuditLog):
    """Automatically computes and attaches previous_hash and record_hash before persisting."""
    if not target.record_hash:
        try:
            # Transaction-scoped chaining cache ensures batches (db.add_all) chain properly
            txn = connection.get_transaction()
            if connection.info.get("_audit_txn") is not txn:
                connection.info["_audit_txn"] = txn
                connection.info["_latest_audit_hash"] = None

            latest_hash = connection.info.get("_latest_audit_hash")
            if not latest_hash:
                stmt = (
                    select(AuditLog.record_hash)
                    .where(AuditLog.record_hash.isnot(None))
                    .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                    .limit(1)
                )
                latest_hash = connection.execute(stmt).scalar()
            target.previous_hash = latest_hash if latest_hash else GENESIS_HASH
        except Exception:
            target.previous_hash = GENESIS_HASH

        target.record_hash = compute_audit_hash(
            previous_hash=target.previous_hash,
            id=target.id,
            timestamp=target.timestamp,
            actor=target.actor,
            actor_type=target.actor_type,
            action=target.action,
            resource=target.resource,
            resource_id=target.resource_id,
            status=target.status,
            module=target.module,
            ip_address=target.ip_address,
            session_id=target.session_id,
            metadata_json=target.metadata_json,
        )
        connection.info["_latest_audit_hash"] = target.record_hash
