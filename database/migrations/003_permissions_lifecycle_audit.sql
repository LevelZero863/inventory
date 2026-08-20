CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    username TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id INTEGER,
    source_no TEXT DEFAULT '',
    before_json TEXT DEFAULT '',
    after_json TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_action ON audit_logs(username, action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);

UPDATE users SET role='viewer' WHERE role NOT IN ('admin','warehouse','finance','viewer');

ALTER TABLE inbound_orders ADD COLUMN void_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE inbound_orders ADD COLUMN voided_at TEXT;
ALTER TABLE inbound_orders ADD COLUMN voided_by TEXT NOT NULL DEFAULT '';

ALTER TABLE outbound_orders ADD COLUMN void_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE outbound_orders ADD COLUMN voided_at TEXT;
ALTER TABLE outbound_orders ADD COLUMN voided_by TEXT NOT NULL DEFAULT '';

ALTER TABLE settlements ADD COLUMN status TEXT NOT NULL DEFAULT '已生效';
ALTER TABLE settlements ADD COLUMN void_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE settlements ADD COLUMN voided_at TEXT;
ALTER TABLE settlements ADD COLUMN voided_by TEXT NOT NULL DEFAULT '';
