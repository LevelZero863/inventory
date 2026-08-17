from __future__ import annotations

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "inventory.db"


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(seed: bool = True) -> None:
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            spec TEXT DEFAULT '',
            unit TEXT NOT NULL DEFAULT '件',
            default_price REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT '启用',
            remark TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL UNIQUE,
            contact TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            settlement_method TEXT NOT NULL DEFAULT '月结',
            status TEXT NOT NULL DEFAULT '启用',
            remark TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS warehouses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS inbound_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL UNIQUE,
            order_date TEXT NOT NULL,
            supplier TEXT DEFAULT '',
            warehouse TEXT NOT NULL,
            operator TEXT DEFAULT '',
            remark TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT '草稿',
            total_amount REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS inbound_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES inbound_orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity REAL NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            amount REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS outbound_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT NOT NULL UNIQUE,
            order_date TEXT NOT NULL,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            warehouse TEXT NOT NULL,
            operator TEXT DEFAULT '',
            remark TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT '草稿',
            total_amount REAL NOT NULL DEFAULT 0,
            settled_amount REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS outbound_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES outbound_orders(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity REAL NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            amount REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            settlement_no TEXT NOT NULL UNIQUE,
            settlement_date TEXT NOT NULL,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            method TEXT NOT NULL DEFAULT '银行转账',
            amount REAL NOT NULL,
            operator TEXT DEFAULT '',
            remark TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settlement_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            settlement_id INTEGER NOT NULL REFERENCES settlements(id),
            outbound_order_id INTEGER NOT NULL REFERENCES outbound_orders(id),
            amount REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventory_txns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            txn_date TEXT NOT NULL,
            warehouse TEXT NOT NULL,
            product_id INTEGER NOT NULL REFERENCES products(id),
            qty REAL NOT NULL,
            txn_type TEXT NOT NULL,
            source_no TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            source_no TEXT,
            operator TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    if seed and conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO products(code,name,spec,unit,default_price) VALUES (?,?,?,?,?)",
            [
                ("P001", "产品A", "规格A", "件", 10),
                ("P002", "产品B", "规格B", "件", 20),
                ("P003", "产品C", "规格C", "箱", 80),
            ],
        )
        conn.executemany("INSERT INTO customers(code,name,contact,settlement_method) VALUES (?,?,?,?)", [
            ("C001", "客户A", "张三", "月结"),
            ("C002", "客户B", "李四", "现结"),
        ])
        conn.executemany("INSERT INTO warehouses(name) VALUES (?)", [("一号仓",), ("二号仓",)])
    conn.commit()
    conn.close()
