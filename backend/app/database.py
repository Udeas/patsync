from sqlalchemy import text
from sqlmodel import create_engine, Session
import os
from dotenv import load_dotenv

from app.status_catalog import PATENT_STATUS_SEED
from app.tm_status_catalog import TM_STATUS_SEED

load_dotenv()

sqlite_url = os.getenv("DATABASE_URL")
engine = create_engine(sqlite_url, echo=True)


def _run_postgres_migrations(conn) -> None:
    status_exists = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'status'
            )
            """
        )
    ).scalar_one()

    status_table_exists = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'status_table'
            )
            """
        )
    ).scalar_one()

    if (not status_exists) and status_table_exists:
        conn.execute(text('ALTER TABLE "status_table" RENAME TO "status"'))
    elif status_exists and status_table_exists:
        conn.execute(
            text(
                """
                INSERT INTO status (id, status)
                SELECT st.id, st.status
                FROM status_table st
                LEFT JOIN status s ON s.id = st.id
                WHERE s.id IS NULL
                """
            )
        )
        conn.execute(
            text(
                """
                DO $$
                DECLARE fk_name text;
                BEGIN
                    SELECT tc.constraint_name INTO fk_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage ccu
                      ON tc.constraint_name = ccu.constraint_name
                     AND tc.table_schema = ccu.table_schema
                    WHERE tc.table_schema = 'public'
                      AND tc.table_name = 'application_state'
                      AND tc.constraint_type = 'FOREIGN KEY'
                      AND kcu.column_name = 'status_id'
                      AND ccu.table_name = 'status_table'
                      AND ccu.column_name = 'id'
                    LIMIT 1;

                    IF fk_name IS NOT NULL THEN
                        EXECUTE format('ALTER TABLE application_state DROP CONSTRAINT %I', fk_name);
                        ALTER TABLE application_state
                        ADD CONSTRAINT fk_application_state_status_id
                        FOREIGN KEY (status_id)
                        REFERENCES status(id);
                    END IF;
                EXCEPTION
                    WHEN duplicate_object THEN
                        NULL;
                END $$;
                """
            )
        )
        conn.execute(text("DROP TABLE status_table"))

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS application_data (
                id SERIAL PRIMARY KEY,
                application_num VARCHAR NOT NULL UNIQUE,
                applicant_name VARCHAR NOT NULL,
                application_title VARCHAR NOT NULL,
                applicant_address TEXT NOT NULL,
                comments TEXT
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS status (
                id INTEGER PRIMARY KEY,
                status VARCHAR NOT NULL UNIQUE
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS application_state (
                id SERIAL PRIMARY KEY,
                application_num VARCHAR NOT NULL REFERENCES application_data(application_num),
                status_id INTEGER NOT NULL REFERENCES status(id),
                application_date DATE NOT NULL
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_application_state_application_num
            ON application_state (application_num);
            """
        )
    )

    conn.execute(
        text(
            """
            ALTER TABLE application_data
            ADD COLUMN IF NOT EXISTS created_date TIMESTAMPTZ;
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE application_data
            ADD COLUMN IF NOT EXISTS modified_date TIMESTAMPTZ;
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE application_data
            SET created_date = COALESCE(created_date, NOW()),
                modified_date = COALESCE(modified_date, NOW());
            """
        )
    )
    conn.execute(text("ALTER TABLE application_data ALTER COLUMN created_date SET NOT NULL"))
    conn.execute(text("ALTER TABLE application_data ALTER COLUMN modified_date SET NOT NULL"))

    conn.execute(
        text(
            """
            ALTER TABLE application_data
            ADD COLUMN IF NOT EXISTS project_code VARCHAR;
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE application_data
            SET project_code = 'PROJ' || id::text
            WHERE project_code IS NULL;
            """
        )
    )
    conn.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_application_data_project_code'
                ) THEN
                    ALTER TABLE application_data
                    ADD CONSTRAINT uq_application_data_project_code UNIQUE (project_code);
                END IF;
            END $$;
            """
        )
    )
    conn.execute(text("ALTER TABLE application_data ALTER COLUMN project_code SET NOT NULL"))

    conn.execute(
        text(
            """
            ALTER TABLE application_data
            ADD COLUMN IF NOT EXISTS last_status_updated_at TIMESTAMPTZ;
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE application_data
            ADD COLUMN IF NOT EXISTS client_id INTEGER;
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE application_data
            ADD COLUMN IF NOT EXISTS attorney_id INTEGER;
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE application_data
            ADD COLUMN IF NOT EXISTS client_docket_no VARCHAR;
            """
        )
    )

    conn.execute(
        text(
            """
            ALTER TABLE application_state
            ADD COLUMN IF NOT EXISTS created_date TIMESTAMPTZ;
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE application_state
            ADD COLUMN IF NOT EXISTS modified_date TIMESTAMPTZ;
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE application_state
            SET created_date = COALESCE(created_date, NOW()),
                modified_date = COALESCE(modified_date, NOW());
            """
        )
    )
    conn.execute(text("ALTER TABLE application_state ALTER COLUMN created_date SET NOT NULL"))
    conn.execute(text("ALTER TABLE application_state ALTER COLUMN modified_date SET NOT NULL"))

    conn.execute(
        text(
            """
            DO $$
            DECLARE fk_name text;
            BEGIN
                SELECT tc.constraint_name INTO fk_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.table_schema = ccu.table_schema
                WHERE tc.table_schema = 'public'
                  AND tc.table_name = 'application_state'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = 'application_num'
                  AND ccu.table_name = 'application_data'
                  AND ccu.column_name = 'application_num'
                LIMIT 1;

                IF fk_name IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE application_state DROP CONSTRAINT %I', fk_name);
                END IF;

                ALTER TABLE application_state
                ADD CONSTRAINT fk_application_state_application_num
                FOREIGN KEY (application_num)
                REFERENCES application_data(application_num)
                ON UPDATE CASCADE
                ON DELETE CASCADE;
            EXCEPTION
                WHEN duplicate_object THEN
                    NULL;
            END $$;
            """
        )
    )

    legacy_table_exists = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'application'
            )
            """
        )
    ).scalar_one()
    if legacy_table_exists:
        conn.execute(text('TRUNCATE TABLE "application" RESTART IDENTITY CASCADE'))

    _run_postgres_tm_migrations(conn)


def _run_postgres_tm_migrations(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS tm_application_data (
                id SERIAL PRIMARY KEY,
                project_code VARCHAR NOT NULL UNIQUE,
                application_num VARCHAR NOT NULL UNIQUE,
                applicant_name VARCHAR NOT NULL,
                tm_name VARCHAR NOT NULL,
                tm_class VARCHAR NOT NULL,
                applicant_address TEXT NOT NULL,
                comments TEXT,
                created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                modified_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_status_updated_at TIMESTAMPTZ
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS tm_status (
                id INTEGER PRIMARY KEY,
                status VARCHAR NOT NULL UNIQUE
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS tm_application_state (
                id SERIAL PRIMARY KEY,
                application_num VARCHAR NOT NULL REFERENCES tm_application_data(application_num)
                    ON UPDATE CASCADE ON DELETE CASCADE,
                status_id INTEGER NOT NULL REFERENCES tm_status(id),
                application_date DATE NOT NULL,
                created_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                modified_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_tm_application_state_application_num
            ON tm_application_state (application_num);
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE tm_application_data
            ADD COLUMN IF NOT EXISTS client_id INTEGER;
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE tm_application_data
            ADD COLUMN IF NOT EXISTS attorney_id INTEGER;
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE tm_application_data
            ADD COLUMN IF NOT EXISTS client_docket_no VARCHAR;
            """
        )
    )


def _sqlite_column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def _run_sqlite_migrations(conn) -> None:
    status_exists = conn.execute(
        text(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='status'
            """
        )
    ).fetchone()
    status_table_exists = conn.execute(
        text(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='status_table'
            """
        )
    ).fetchone()

    if (not status_exists) and status_table_exists:
        conn.execute(text("ALTER TABLE status_table RENAME TO status"))
    elif status_exists and status_table_exists:
        conn.execute(
            text(
                """
                INSERT INTO status (id, status)
                SELECT st.id, st.status
                FROM status_table st
                LEFT JOIN status s ON s.id = st.id
                WHERE s.id IS NULL
                """
            )
        )
        conn.execute(text("DROP TABLE status_table"))

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS application_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_code TEXT NOT NULL UNIQUE,
                application_num TEXT NOT NULL UNIQUE,
                applicant_name TEXT NOT NULL,
                application_title TEXT NOT NULL,
                applicant_address TEXT NOT NULL,
                comments TEXT,
                created_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                modified_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_status_updated_at TEXT
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS status (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL UNIQUE
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS application_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_num TEXT NOT NULL,
                status_id INTEGER NOT NULL,
                application_date DATE NOT NULL,
                created_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                modified_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(application_num) REFERENCES application_data(application_num) ON UPDATE CASCADE ON DELETE CASCADE,
                FOREIGN KEY(status_id) REFERENCES status(id)
            );
            """
        )
    )

    if not _sqlite_column_exists(conn, "application_data", "project_code"):
        conn.execute(text("ALTER TABLE application_data ADD COLUMN project_code TEXT"))
        conn.execute(
            text(
                """
                UPDATE application_data
                SET project_code = 'PROJ' || id
                WHERE project_code IS NULL
                """
            )
        )
    if not _sqlite_column_exists(conn, "application_data", "last_status_updated_at"):
        conn.execute(text("ALTER TABLE application_data ADD COLUMN last_status_updated_at TEXT"))
    if not _sqlite_column_exists(conn, "application_data", "client_id"):
        conn.execute(text("ALTER TABLE application_data ADD COLUMN client_id INTEGER"))
    if not _sqlite_column_exists(conn, "application_data", "attorney_id"):
        conn.execute(text("ALTER TABLE application_data ADD COLUMN attorney_id INTEGER"))
    if not _sqlite_column_exists(conn, "application_data", "client_docket_no"):
        conn.execute(text("ALTER TABLE application_data ADD COLUMN client_docket_no TEXT"))
    if not _sqlite_column_exists(conn, "application_data", "created_date"):
        conn.execute(
            text("ALTER TABLE application_data ADD COLUMN created_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        )
    if not _sqlite_column_exists(conn, "application_data", "modified_date"):
        conn.execute(
            text("ALTER TABLE application_data ADD COLUMN modified_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        )
    if not _sqlite_column_exists(conn, "application_state", "created_date"):
        conn.execute(
            text("ALTER TABLE application_state ADD COLUMN created_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        )
    if not _sqlite_column_exists(conn, "application_state", "modified_date"):
        conn.execute(
            text("ALTER TABLE application_state ADD COLUMN modified_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        )

    conn.execute(
        text(
            """
            UPDATE application_data
            SET created_date = COALESCE(created_date, CURRENT_TIMESTAMP),
                modified_date = COALESCE(modified_date, CURRENT_TIMESTAMP)
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE application_state
            SET created_date = COALESCE(created_date, CURRENT_TIMESTAMP),
                modified_date = COALESCE(modified_date, CURRENT_TIMESTAMP)
            """
        )
    )

    legacy_sqlite_exists = conn.execute(
        text(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name='application'
            """
        )
    ).fetchone()
    if legacy_sqlite_exists:
        conn.execute(text("DELETE FROM application"))

    _run_sqlite_tm_migrations(conn)


def _run_sqlite_tm_migrations(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS tm_application_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_code TEXT NOT NULL UNIQUE,
                application_num TEXT NOT NULL UNIQUE,
                applicant_name TEXT NOT NULL,
                tm_name TEXT NOT NULL,
                tm_class TEXT NOT NULL,
                applicant_address TEXT NOT NULL,
                comments TEXT,
                created_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                modified_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_status_updated_at TEXT
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS tm_status (
                id INTEGER PRIMARY KEY,
                status TEXT NOT NULL UNIQUE
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS tm_application_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_num TEXT NOT NULL,
                status_id INTEGER NOT NULL,
                application_date DATE NOT NULL,
                created_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                modified_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(application_num) REFERENCES tm_application_data(application_num)
                    ON UPDATE CASCADE ON DELETE CASCADE,
                FOREIGN KEY(status_id) REFERENCES tm_status(id)
            );
            """
        )
    )
    if not _sqlite_column_exists(conn, "tm_application_data", "client_id"):
        conn.execute(text("ALTER TABLE tm_application_data ADD COLUMN client_id INTEGER"))
    if not _sqlite_column_exists(conn, "tm_application_data", "attorney_id"):
        conn.execute(text("ALTER TABLE tm_application_data ADD COLUMN attorney_id INTEGER"))
    if not _sqlite_column_exists(conn, "tm_application_data", "client_docket_no"):
        conn.execute(text("ALTER TABLE tm_application_data ADD COLUMN client_docket_no TEXT"))


def _seed_patent_statuses(conn, backend: str) -> None:
    conflict_update = (
        "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status"
        if backend == "postgresql"
        else "ON CONFLICT (id) DO UPDATE SET status = excluded.status"
    )
    sql = text(
        f"""
        INSERT INTO status (id, status) VALUES (:id, :lbl)
        {conflict_update}
        """
    )
    for sid, lbl in PATENT_STATUS_SEED:
        conn.execute(sql, {"id": sid, "lbl": lbl})


def _seed_tm_statuses(conn, backend: str) -> None:
    conflict_update = (
        "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status"
        if backend == "postgresql"
        else "ON CONFLICT (id) DO UPDATE SET status = excluded.status"
    )
    sql = text(
        f"""
        INSERT INTO tm_status (id, status) VALUES (:id, :lbl)
        {conflict_update}
        """
    )
    for sid, lbl in TM_STATUS_SEED:
        conn.execute(sql, {"id": sid, "lbl": lbl})


def _postgres_column_exists(conn, table_name: str, column_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                      AND column_name = :column_name
                )
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).scalar_one()
    )


def _run_patent_metadata_migrations(conn, backend: str) -> None:
    if backend == "postgresql":
        if not _postgres_column_exists(conn, "patent_project", "application_type"):
            conn.execute(text("ALTER TABLE patent_project ADD COLUMN application_type VARCHAR"))
        if not _postgres_column_exists(conn, "patent_project", "provisional_kind"):
            conn.execute(text("ALTER TABLE patent_project ADD COLUMN provisional_kind VARCHAR(3)"))
        if not _postgres_column_exists(conn, "patent_project", "pct_wipo_filed_only"):
            conn.execute(
                text(
                    "ALTER TABLE patent_project ADD COLUMN pct_wipo_filed_only BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
        if not _postgres_column_exists(conn, "patent_project", "is_archived"):
            conn.execute(
                text(
                    "ALTER TABLE patent_project ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = 'patent_client'
                    ) THEN
                        ALTER TABLE patent_client ALTER COLUMN client_code TYPE VARCHAR(10);
                    END IF;
                END $$;
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS patent_international_application (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES patent_project(id),
                    international_application_no VARCHAR NOT NULL,
                    international_application_date DATE NOT NULL
                );
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS patent_applicant (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES patent_project(id),
                    name VARCHAR NOT NULL,
                    country VARCHAR(2),
                    address TEXT
                );
                """
            )
        )
        return

    if _sqlite_column_exists(conn, "patent_project", "id"):
        if not _sqlite_column_exists(conn, "patent_project", "application_type"):
            conn.execute(text("ALTER TABLE patent_project ADD COLUMN application_type TEXT"))
        if not _sqlite_column_exists(conn, "patent_project", "provisional_kind"):
            conn.execute(text("ALTER TABLE patent_project ADD COLUMN provisional_kind TEXT"))
        if not _sqlite_column_exists(conn, "patent_project", "pct_wipo_filed_only"):
            conn.execute(
                text(
                    "ALTER TABLE patent_project ADD COLUMN pct_wipo_filed_only BOOLEAN NOT NULL DEFAULT 0"
                )
            )
        if not _sqlite_column_exists(conn, "patent_project", "is_archived"):
            conn.execute(
                text(
                    "ALTER TABLE patent_project ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0"
                )
            )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS patent_international_application (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES patent_project(id),
                international_application_no TEXT NOT NULL,
                international_application_date DATE NOT NULL
            );
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS patent_applicant (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES patent_project(id),
                name TEXT NOT NULL,
                country TEXT,
                address TEXT
            );
            """
        )
    )


def _run_uspto_tracker_migration(conn, backend: str) -> None:
    if backend == "postgresql":
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS uspto_tracker (
                    id SERIAL PRIMARY KEY,
                    docket_no VARCHAR(64) NOT NULL,
                    application_no VARCHAR(32) NOT NULL DEFAULT '',
                    doc_code VARCHAR(32) NOT NULL,
                    particulars TEXT NOT NULL DEFAULT '',
                    event_date VARCHAR(16) NOT NULL,
                    final_due_date DATE,
                    work_status VARCHAR(32) NOT NULL DEFAULT 'Pending',
                    calendar_event_ids TEXT NOT NULL DEFAULT '',
                    template_status VARCHAR(64) NOT NULL DEFAULT '',
                    is_closure_done BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_uspto_tracker_natural_key
                        UNIQUE (docket_no, doc_code, event_date, application_no)
                );
                """
            )
        )
    else:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS uspto_tracker (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    docket_no TEXT NOT NULL,
                    application_no TEXT NOT NULL DEFAULT '',
                    doc_code TEXT NOT NULL,
                    particulars TEXT NOT NULL DEFAULT '',
                    event_date TEXT NOT NULL,
                    final_due_date TEXT,
                    work_status TEXT NOT NULL DEFAULT 'Pending',
                    calendar_event_ids TEXT NOT NULL DEFAULT '',
                    template_status TEXT NOT NULL DEFAULT '',
                    is_closure_done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE (docket_no, doc_code, event_date, application_no)
                );
                """
            )
        )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_uspto_tracker_doc_code ON uspto_tracker (doc_code)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_uspto_tracker_work_status ON uspto_tracker (work_status)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_uspto_tracker_docket_no ON uspto_tracker (docket_no)"
        )
    )
    if backend == "postgresql":
        conn.execute(
            text(
                "ALTER TABLE uspto_tracker ADD COLUMN IF NOT EXISTS completion_date DATE"
            )
        )
    else:
        cols = conn.execute(text("PRAGMA table_info(uspto_tracker)")).fetchall()
        col_names = {row[1] for row in cols} if cols else set()
        if "completion_date" not in col_names:
            conn.execute(text("ALTER TABLE uspto_tracker ADD COLUMN completion_date TEXT"))


def run_schema_migrations():
    backend = engine.url.get_backend_name()
    with engine.begin() as conn:
        if backend == "postgresql":
            _run_postgres_migrations(conn)
        else:
            _run_sqlite_migrations(conn)
        _run_patent_metadata_migrations(conn, backend)
        _run_uspto_tracker_migration(conn, backend)
        _seed_patent_statuses(conn, backend)
        _seed_tm_statuses(conn, backend)


def get_session():
    with Session(engine) as session:
        yield session
