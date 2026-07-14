USE public_opinion;

CREATE TABLE IF NOT EXISTS event_heat_history (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_id BIGINT NOT NULL,
    heat FLOAT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    stage_snapshot VARCHAR(20) NULL,
    PRIMARY KEY (id),
    INDEX idx_event_heat_history_event_created (event_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
