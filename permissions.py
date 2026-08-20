from __future__ import annotations


ROLE_LABELS = {
    "admin": "管理员",
    "warehouse": "仓库人员",
    "finance": "财务人员",
    "viewer": "只读人员",
}

ALL_PERMISSIONS = {
    "view",
    "manage_master",
    "create_inbound",
    "create_outbound",
    "create_settlement",
    "void_inbound",
    "void_outbound",
    "void_settlement",
    "manage_users",
    "view_audit",
    "backup_database",
}

ROLE_PERMISSIONS = {
    "admin": ALL_PERMISSIONS,
    "warehouse": {"view", "create_inbound", "create_outbound"},
    "finance": {"view", "create_settlement", "void_settlement"},
    "viewer": {"view"},
}


def normalize_actor(actor) -> dict:
    if actor is None:
        return {"id": None, "username": "system", "display_name": "系统", "role": "admin"}
    return {
        "id": actor.get("id"),
        "username": str(actor.get("username") or "").strip(),
        "display_name": str(actor.get("display_name") or "").strip(),
        "role": str(actor.get("role") or "viewer"),
    }


def has_permission(actor, permission: str) -> bool:
    normalized = normalize_actor(actor)
    return permission in ROLE_PERMISSIONS.get(normalized["role"], set())


def require_permission(actor, permission: str) -> None:
    if not has_permission(actor, permission):
        raise PermissionError("当前账号没有执行此操作的权限")
