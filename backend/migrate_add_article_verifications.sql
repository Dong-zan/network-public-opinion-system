USE public_opinion;

CREATE TABLE IF NOT EXISTS article_verifications (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_id BIGINT NOT NULL,
    news_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    overall_verdict VARCHAR(50) NOT NULL,
    evidence_score FLOAT NOT NULL,
    result_json JSON NOT NULL,
    provider VARCHAR(50) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_article_verifications_event_news_created (
        event_id,
        news_id,
        created_at
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
