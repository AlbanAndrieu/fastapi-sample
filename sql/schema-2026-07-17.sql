BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 992855f73a8d

CREATE TABLE "user" (
    id SERIAL NOT NULL,
    name VARCHAR(50) NOT NULL,
    email VARCHAR(50) NOT NULL,
    description VARCHAR(200),
    PRIMARY KEY (id)
);

ALTER TABLE "user" ADD COLUMN created_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE note ADD COLUMN type VARCHAR(10) NOT NULL;

ALTER TABLE note ADD COLUMN prompt VARCHAR(100) NOT NULL;

INSERT INTO alembic_version (version_num) VALUES ('992855f73a8d') RETURNING alembic_version.version_num;

COMMIT;
