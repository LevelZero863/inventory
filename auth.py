from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from audit import write_audit
from db import get_conn
from permissions import ROLE_LABELS, require_permission

HASH_NAME = "sha256"
HASH_ITERATIONS = 310_000
INITIAL_ADMIN_USERNAME = os.getenv("INVENTORY_INITIAL_ADMIN_USERNAME", "admin")
INITIAL_ADMIN_PASSWORD = os.getenv("INVENTORY_INITIAL_ADMIN_PASSWORD", "admin123")


def hash_password(password: str, salt: str | None = None) -> str:
    if len(password) < 8:
        raise ValueError("密码长度至少为 8 位")
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        HASH_NAME, password.encode("utf-8"), bytes.fromhex(salt), HASH_ITERATIONS
    ).hex()
    return f"pbkdf2_{HASH_NAME}${HASH_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != f"pbkdf2_{HASH_NAME}":
            return False
        actual = hashlib.pbkdf2_hmac(
            HASH_NAME,
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def ensure_initial_admin() -> bool:
    """Create the first administrator only when the users table is empty."""
    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return False
        conn.execute(
            """INSERT INTO users(
                   username,password_hash,display_name,role,must_change_password
               ) VALUES(?,?,?,?,1)""",
            (
                INITIAL_ADMIN_USERNAME,
                hash_password(INITIAL_ADMIN_PASSWORD),
                "系统管理员",
                "admin",
            ),
        )
        write_audit(
            "创建初始管理员",
            entity_type="用户",
            entity_id=conn.execute("SELECT last_insert_rowid()").fetchone()[0],
            source_no=INITIAL_ADMIN_USERNAME,
            after={"username": INITIAL_ADMIN_USERNAME, "role": "admin", "is_active": 1},
            conn=conn,
        )
        conn.commit()
        return True
    finally:
        conn.close()


def authenticate(username: str, password: str):
    username = username.strip()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id,username,password_hash,display_name,role,must_change_password
               FROM users WHERE username=? AND is_active=1""",
            (username,),
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            write_audit(
                "登录失败",
                {"id": row["id"] if row else None, "username": username, "role": "viewer"},
                entity_type="用户",
                entity_id=row["id"] if row else None,
                source_no=username,
                detail="账号不存在、已停用或密码错误",
                conn=conn,
            )
            conn.commit()
            return None
        conn.execute(
            "UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],)
        )
        user = {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "must_change_password": bool(row["must_change_password"]),
        }
        write_audit(
            "登录成功", user, entity_type="用户", entity_id=row["id"], source_no=username, conn=conn
        )
        conn.commit()
        return user
    finally:
        conn.close()


def change_password(user_id: int, new_password: str, actor=None) -> None:
    encoded = hash_password(new_password)
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE users
               SET password_hash=?,must_change_password=0,updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND is_active=1""",
            (encoded, user_id),
        )
        if cur.rowcount != 1:
            raise ValueError("账号不存在或已停用")
        acting_user = actor or {"id": user_id, "username": "self", "role": "viewer"}
        write_audit(
            "修改密码", acting_user, entity_type="用户", entity_id=user_id,
            after={"password_changed": True}, conn=conn,
        )
        conn.commit()
    finally:
        conn.close()


def get_active_user(user_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id,username,display_name,role,must_change_password
               FROM users WHERE id=? AND is_active=1""",
            (int(user_id),),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "username": row["username"],
            "display_name": row["display_name"], "role": row["role"],
            "must_change_password": bool(row["must_change_password"]),
        }
    finally:
        conn.close()


def list_users(actor=None):
    require_permission(actor, "manage_users")
    conn = get_conn()
    try:
        return conn.execute(
            """SELECT id,username,display_name,role,is_active,must_change_password,
                      last_login_at,created_at,updated_at
               FROM users ORDER BY id"""
        ).fetchall()
    finally:
        conn.close()


def create_user(username, display_name, role, password, actor=None) -> int:
    require_permission(actor, "manage_users")
    username = str(username).strip()
    display_name = str(display_name).strip()
    if not username or not display_name:
        raise ValueError("账号和姓名不能为空")
    if role not in ROLE_LABELS:
        raise ValueError("用户角色无效")
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        cur = conn.execute(
            """INSERT INTO users(
                   username,password_hash,display_name,role,is_active,must_change_password
               ) VALUES(?,?,?,?,1,1)""",
            (username, hash_password(password), display_name, role),
        )
        user_id = int(cur.lastrowid)
        write_audit(
            "新增用户", actor, entity_type="用户", entity_id=user_id, source_no=username,
            after={"username": username, "display_name": display_name, "role": role, "is_active": 1},
            conn=conn,
        )
        conn.commit()
        return user_id
    except Exception as exc:
        conn.rollback()
        if "unique" in str(exc).lower():
            raise ValueError("账号已存在") from exc
        raise
    finally:
        conn.close()


def update_user(user_id, display_name, role, is_active, actor=None) -> None:
    require_permission(actor, "manage_users")
    if role not in ROLE_LABELS:
        raise ValueError("用户角色无效")
    is_active = 1 if bool(is_active) else 0
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        before = conn.execute(
            "SELECT id,username,display_name,role,is_active FROM users WHERE id=?", (int(user_id),)
        ).fetchone()
        if not before:
            raise ValueError("账号不存在")
        if actor and int(actor.get("id") or 0) == int(user_id) and not is_active:
            raise ValueError("不能停用当前登录账号")
        if before["role"] == "admin" and before["is_active"] and (role != "admin" or not is_active):
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1"
            ).fetchone()[0]
            if active_admins <= 1:
                raise ValueError("系统必须至少保留一个启用的管理员")
        conn.execute(
            """UPDATE users SET display_name=?,role=?,is_active=?,updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (str(display_name).strip(), role, is_active, int(user_id)),
        )
        after = {
            "id": int(user_id), "username": before["username"],
            "display_name": str(display_name).strip(), "role": role, "is_active": is_active,
        }
        write_audit(
            "修改用户", actor, entity_type="用户", entity_id=int(user_id),
            source_no=before["username"], before=before, after=after, conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset_user_password(user_id, new_password, actor=None) -> None:
    require_permission(actor, "manage_users")
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        row = conn.execute("SELECT username FROM users WHERE id=?", (int(user_id),)).fetchone()
        if not row:
            raise ValueError("账号不存在")
        conn.execute(
            """UPDATE users SET password_hash=?,must_change_password=1,
                      updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (hash_password(new_password), int(user_id)),
        )
        write_audit(
            "重置用户密码", actor, entity_type="用户", entity_id=int(user_id),
            source_no=row["username"], after={"must_change_password": 1}, conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
