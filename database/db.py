import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_date TEXT NOT NULL,
                    slot_time TEXT NOT NULL,
                    is_closed INTEGER DEFAULT 0,
                    UNIQUE(slot_date, slot_time)
                );

                CREATE TABLE IF NOT EXISTS closed_days (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slot_date TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    parent_name TEXT NOT NULL,
                    child_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    slot_date TEXT NOT NULL,
                    slot_time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    reminder_job_id TEXT,
                    reminder_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_bookings_user_status ON bookings(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(slot_date);
                """
            )
            conn.commit()

    def get_user_active_booking(self, user_id: int) -> sqlite3.Row | None:
        with closing(self._connect()) as conn:
            return conn.execute(
                "SELECT * FROM bookings WHERE user_id = ? AND status = 'active' LIMIT 1",
                (user_id,),
            ).fetchone()

    def is_day_closed(self, date_iso: str) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM closed_days WHERE slot_date = ? LIMIT 1", (date_iso,)
            ).fetchone()
            return row is not None

    def close_day(self, date_iso: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO closed_days(slot_date) VALUES (?)",
                (date_iso,),
            )
            conn.commit()

    def open_day(self, date_iso: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM closed_days WHERE slot_date = ?", (date_iso,))
            conn.commit()

    def add_slot(self, date_iso: str, time_str: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO slots(slot_date, slot_time) VALUES (?, ?)",
                (date_iso, time_str),
            )
            conn.commit()

    def remove_slot(self, date_iso: str, time_str: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                DELETE FROM slots
                WHERE slot_date = ? AND slot_time = ?
                AND NOT EXISTS (
                    SELECT 1 FROM bookings
                    WHERE bookings.slot_date = slots.slot_date
                    AND bookings.slot_time = slots.slot_time
                    AND bookings.status = 'active'
                )
                """,
                (date_iso, time_str),
            )
            conn.commit()

    def get_available_dates(self, start_date: str, end_date: str) -> list[str]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT s.slot_date
                FROM slots s
                LEFT JOIN bookings b
                    ON b.slot_date = s.slot_date
                    AND b.slot_time = s.slot_time
                    AND b.status = 'active'
                LEFT JOIN closed_days cd ON cd.slot_date = s.slot_date
                WHERE s.slot_date BETWEEN ? AND ?
                  AND cd.slot_date IS NULL
                  AND b.id IS NULL
                ORDER BY s.slot_date ASC
                """,
                (start_date, end_date),
            ).fetchall()
            return [row["slot_date"] for row in rows]

    def get_available_times(self, date_iso: str) -> list[str]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT s.slot_time
                FROM slots s
                LEFT JOIN bookings b
                    ON b.slot_date = s.slot_date
                    AND b.slot_time = s.slot_time
                    AND b.status = 'active'
                LEFT JOIN closed_days cd ON cd.slot_date = s.slot_date
                WHERE s.slot_date = ?
                  AND cd.slot_date IS NULL
                  AND b.id IS NULL
                ORDER BY s.slot_time ASC
                """,
                (date_iso,),
            ).fetchall()
            return [row["slot_time"] for row in rows]

    def create_booking(
        self,
        user_id: int,
        parent_name: str,
        child_name: str,
        phone: str,
        slot_date: str,
        slot_time: str,
    ) -> int | None:
        with closing(self._connect()) as conn:
            with conn:
                exists = conn.execute(
                    "SELECT id FROM bookings WHERE user_id = ? AND status = 'active' LIMIT 1",
                    (user_id,),
                ).fetchone()
                if exists is not None:
                    return None

                is_free = conn.execute(
                    """
                    SELECT s.id
                    FROM slots s
                    LEFT JOIN closed_days cd ON cd.slot_date = s.slot_date
                    LEFT JOIN bookings b
                      ON b.slot_date = s.slot_date
                      AND b.slot_time = s.slot_time
                      AND b.status = 'active'
                    WHERE s.slot_date = ? AND s.slot_time = ?
                      AND cd.slot_date IS NULL
                      AND b.id IS NULL
                    LIMIT 1
                    """,
                    (slot_date, slot_time),
                ).fetchone()
                if is_free is None:
                    return None

                cur = conn.execute(
                    """
                    INSERT INTO bookings(
                        user_id, parent_name, child_name, phone,
                        slot_date, slot_time, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        parent_name,
                        child_name,
                        phone,
                        slot_date,
                        slot_time,
                        datetime.utcnow().isoformat(),
                    ),
                )
                return int(cur.lastrowid)

    def get_booking_by_id(self, booking_id: int) -> sqlite3.Row | None:
        with closing(self._connect()) as conn:
            return conn.execute(
                "SELECT * FROM bookings WHERE id = ? LIMIT 1", (booking_id,)
            ).fetchone()

    def cancel_booking(self, booking_id: int) -> bool:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'",
                (booking_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def cancel_user_booking(self, user_id: int) -> sqlite3.Row | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE user_id = ? AND status = 'active' LIMIT 1",
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (row["id"],))
            conn.commit()
            return row

    def set_reminder(self, booking_id: int, job_id: str | None, reminder_at: str | None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE bookings SET reminder_job_id = ?, reminder_at = ? WHERE id = ?",
                (job_id, reminder_at, booking_id),
            )
            conn.commit()

    def get_future_active_bookings_with_reminders(self) -> list[sqlite3.Row]:
        now = datetime.utcnow().isoformat()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM bookings
                WHERE status = 'active'
                  AND reminder_job_id IS NOT NULL
                  AND reminder_at IS NOT NULL
                  AND reminder_at > ?
                """,
                (now,),
            ).fetchall()
            return rows

    def get_date_bookings(self, date_iso: str) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            return conn.execute(
                """
                SELECT *
                FROM bookings
                WHERE slot_date = ? AND status = 'active'
                ORDER BY slot_time ASC
                """,
                (date_iso,),
            ).fetchall()

    def get_slots_for_date(self, date_iso: str) -> list[str]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT slot_time FROM slots WHERE slot_date = ? ORDER BY slot_time ASC",
                (date_iso,),
            ).fetchall()
            return [row["slot_time"] for row in rows]

    def get_all_active_bookings(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE status = 'active' ORDER BY slot_date, slot_time"
            ).fetchall()
            return [dict(row) for row in rows]
