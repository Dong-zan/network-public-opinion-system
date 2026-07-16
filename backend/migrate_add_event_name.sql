-- Add an optional display name without changing existing event identity or data.
ALTER TABLE events
    ADD COLUMN event_name VARCHAR(20) NULL COMMENT '事件展示名称' AFTER title;
