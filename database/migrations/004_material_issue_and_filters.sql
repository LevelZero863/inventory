ALTER TABLE outbound_orders ADD COLUMN outbound_type TEXT NOT NULL DEFAULT '销售出库';
ALTER TABLE outbound_orders ADD COLUMN material_recipient TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_inbound_orders_date ON inbound_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_outbound_orders_date_type ON outbound_orders(order_date,outbound_type);
CREATE INDEX IF NOT EXISTS idx_settlements_date ON settlements(settlement_date);
CREATE INDEX IF NOT EXISTS idx_inventory_txns_date_warehouse ON inventory_txns(txn_date,warehouse);
