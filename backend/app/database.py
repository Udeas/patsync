from sqlmodel import create_engine, Session
from sqlalchemy import text
import os
from dotenv import load_dotenv

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
                application_num TEXT NOT NULL UNIQUE,
                applicant_name TEXT NOT NULL,
                application_title TEXT NOT NULL,
                applicant_address TEXT NOT NULL,
                comments TEXT,
                created_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                modified_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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


def run_schema_migrations():
    backend = engine.url.get_backend_name()
    with engine.begin() as conn:
        if backend == "postgresql":
            _run_postgres_migrations(conn)
            return
        _run_sqlite_migrations(conn)


def get_session():
    with Session(engine) as session:
        yield session
