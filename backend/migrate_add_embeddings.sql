USE public_opinion;

ALTER TABLE analysis
    ADD COLUMN embedding JSON NULL;

ALTER TABLE events
    ADD COLUMN embedding JSON NULL;

ALTER TABLE events
    ADD COLUMN embedding_count INT NOT NULL DEFAULT 1;
