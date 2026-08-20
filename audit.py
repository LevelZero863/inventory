from __future__ import annotations

import json

from db import get_conn
from permissions import normalize_actor, require_permission


def _json_value(value) -> str:
    if value in (None, ""):
        return ""
    if hasattr(value, "keys"):
        value = {key: value[key] for key in value.keys()}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def write_audit(
    action: str,
    actor=None,
    *,
    entity_type: str = "",
    entity_id: int | None = None,
    source_no: str = "",
    before=None,
    after=None,
    detail: str = "",
    conn=None,
) -> None:
    actor = normalize_actor(actor)
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        conn.execute(
            """INSERT INTO audit_logs(
                   user_id,username,action,entity_type,entity_id,source_no,
                   before_json,after_json,detail
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                actor["id"], actor["username"], action, entity_type, entity_id,
                source_no, _json_value(before), _json_value(after), str(detail).strip(),
            ),
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def list_audit_logs(limit: int = 1000, actor=None):
    require_permission(actor, "view_audit")
    conn = get_conn()
    try:
        return conn.execute(
            """SELECT id,created_at,username,action,entity_type,entity_id,
                      source_no,before_json,after_json,detail
               FROM audit_logs ORDER BY id DESC LIMIT ?""",
            (max(1, min(int(limit), 5000)),),
        ).fetchall()
    finally:
        conn.close()
