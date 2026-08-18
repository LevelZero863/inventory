from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from db import get_conn

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
        conn.commit()
        return True
    finally:
        conn.close()


def authenticate(username: str, password: str):
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT id,username,password_hash,display_name,role,must_change_password
               FROM users WHERE username=? AND is_active=1""",
            (username.strip(),),
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        conn.execute(
            "UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],)
        )
        conn.commit()
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "must_change_password": bool(row["must_change_password"]),
        }
    finally:
        conn.close()


def change_password(user_id: int, new_password: str) -> None:
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
        conn.commit()
    finally:
        conn.close()
