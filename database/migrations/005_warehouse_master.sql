ALTER TABLE warehouses ADD COLUMN code TEXT NOT NULL DEFAULT '';
ALTER TABLE warehouses ADD COLUMN status TEXT NOT NULL DEFAULT '启用';
ALTER TABLE warehouses ADD COLUMN remark TEXT NOT NULL DEFAULT '';

UPDATE warehouses SET code='WH' || printf('%03d',id) WHERE code='';

CREATE UNIQUE INDEX IF NOT EXISTS idx_warehouses_code ON warehouses(code);
CREATE INDEX IF NOT EXISTS idx_warehouses_status ON warehouses(status);
