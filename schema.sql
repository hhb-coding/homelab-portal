-- HomeLab Portal database schema
-- HomeLab Portal 数据库结构


-- Main device registry.
-- 设备主表。
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    hostname TEXT,
    display_name TEXT,

    -- Primary local network address.
    -- 主要局域网地址。
    lan_ip TEXT,

    -- Optional ZeroTier address.
    -- 可选的 ZeroTier 地址。
    zerotier_ip TEXT,

    -- Future link to the same device in Beszel.
    -- 后续用于关联 Beszel 中对应的设备。
    beszel_system_id TEXT,

    last_seen TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);


-- Device IP change history.
-- 设备 IP 变化历史。
CREATE TABLE IF NOT EXISTS ip_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    device_id TEXT NOT NULL,

    event_type TEXT NOT NULL,

    old_ip TEXT,
    new_ip TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (device_id)
        REFERENCES devices(device_id)
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_devices_last_seen
ON devices(last_seen);


CREATE INDEX IF NOT EXISTS idx_ip_events_device
ON ip_events(device_id);


CREATE INDEX IF NOT EXISTS idx_ip_events_created
ON ip_events(created_at);

-- Temporary telemetry inbox + 24h receipts; not a history database.
-- 临时频率队列及短期幂等回执，不承担长期历史存储。
CREATE TABLE IF NOT EXISTS frequency_inbox (
    device_id TEXT NOT NULL,
    sample_id TEXT NOT NULL,
    received_utc TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_bytes INTEGER NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (device_id, sample_id)
);
CREATE INDEX IF NOT EXISTS frequency_inbox_received ON frequency_inbox(received_utc);
CREATE TABLE IF NOT EXISTS frequency_queue_status (
    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
    expired INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO frequency_queue_status VALUES (1,0);


-- One Beszel system may only be linked to one HomeLab Portal device.
-- 一个 Beszel system 只能绑定一个 HomeLab Portal 设备。
CREATE UNIQUE INDEX IF NOT EXISTS
idx_devices_beszel_system_id_unique
ON devices(beszel_system_id)
WHERE beszel_system_id IS NOT NULL;
