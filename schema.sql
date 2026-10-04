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
