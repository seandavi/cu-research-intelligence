-- Overlay schema for the application backend (ADR-0026).
-- Holds only user/review-created state; the analytics facts stay in the
-- read-only serving.duckdb. Applied idempotently at startup (init_schema).

-- One row per authenticated identity (Google OIDC subject).
CREATE TABLE IF NOT EXISTS app_user (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    google_sub    TEXT UNIQUE,               -- OIDC subject (stable per Google acct)
    email         TEXT NOT NULL,
    name          TEXT,
    member_id     BIGINT,                     -- resolved cancer-center member (nullable)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS app_user_email_key ON app_user (lower(email));

-- Authorization roles (see app/roles.py). No row => viewer.
CREATE TABLE IF NOT EXISTS user_role (
    user_id    BIGINT NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    granted_by BIGINT REFERENCES app_user (id),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role)
);

-- Member-editable profile content, merged onto the analytics member_profile at
-- read time (snapshot ⊕ overlay). Keyed by cancer-center member_id.
CREATE TABLE IF NOT EXISTS profile (
    member_id  BIGINT PRIMARY KEY,
    bio        TEXT,
    keywords   TEXT[] NOT NULL DEFAULT '{}',
    links      JSONB  NOT NULL DEFAULT '[]',   -- [{label, url}, ...]
    photo_url  TEXT,
    updated_by BIGINT REFERENCES app_user (id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Publication claim/disclaim corrections (the entity-resolution audit, ADR-0026).
CREATE TABLE IF NOT EXISTS pub_correction (
    member_id  BIGINT NOT NULL,
    work_id    TEXT   NOT NULL,
    action     TEXT   NOT NULL CHECK (action IN ('claim', 'disclaim')),
    created_by BIGINT REFERENCES app_user (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (member_id, work_id)
);
