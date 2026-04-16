"""
memory/memory_store.py
-----------------------
Local SQLite storage for behavioral event tokens.

PRIVACY NOTE:
- Raw sensor data is NEVER stored
- Only abstract tokens like <DeepFocus, 14:00, Weekday, focus> are stored
- All data stays on local machine only

Tables:
1. events - stores each recognized behavioral event
2. habits - stores detected recurring patterns (for preemptive behavior)
"""

import sqlite3
import time
import datetime
import os
from pathlib import Path

# Database file location
DB_PATH = Path(__file__).parent / "anima_memory.db"


def get_connection():
    """Get SQLite connection. Creates DB if it doesn't exist."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # Returns dict-like rows
    return conn


def initialize_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Events table - one row per detected behavioral event
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   REAL NOT NULL,
            token       TEXT NOT NULL,
            emotion     TEXT NOT NULL,
            scenario    TEXT NOT NULL,
            hour_of_day INTEGER,
            day_of_week INTEGER,
            day_type    TEXT
        )
    """)

    # Habits table - detected recurring patterns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS habits (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_key     TEXT NOT NULL UNIQUE,
            count           INTEGER DEFAULT 1,
            first_seen      REAL,
            last_seen       REAL,
            preemptive_flag INTEGER DEFAULT 0,
            emotion         TEXT
        )
    """)

    conn.commit()
    conn.close()
    print(f"[MEMORY] Database initialized at {DB_PATH}")


def save_event(token: str, emotion: str, scenario: str, state: dict):
    """
    Save a behavioral event token to the database.
    Raw state data is NOT stored - only the abstract token.
    """
    now = datetime.datetime.now()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO events (timestamp, token, emotion, scenario, 
                               hour_of_day, day_of_week, day_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time(),
            token,
            emotion,
            scenario,
            now.hour,
            now.weekday(),
            "Weekend" if now.weekday() >= 5 else "Weekday"
        ))

        conn.commit()
        conn.close()

        # Check for habit patterns after saving
        _check_habits(emotion, now.hour, now.weekday())

    except Exception as e:
        print(f"[MEMORY] Error saving event: {e}")


def _check_habits(emotion: str, hour: int, day_of_week: int):
    """
    Check if this emotion at this time is a recurring pattern.
    If same emotion appears 3+ times in same hour on same day type,
    set preemptive_flag = 1 (robot will anticipate next time).
    """
    day_type = "Weekend" if day_of_week >= 5 else "Weekday"
    pattern_key = f"{emotion}_{hour:02d}_{day_type}"

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if pattern exists
        cursor.execute(
            "SELECT id, count FROM habits WHERE pattern_key = ?",
            (pattern_key,)
        )
        row = cursor.fetchone()

        if row:
            new_count = row["count"] + 1
            # After 3 occurrences, flag for preemptive behavior
            preemptive = 1 if new_count >= 3 else 0

            cursor.execute("""
                UPDATE habits
                SET count = ?, last_seen = ?, preemptive_flag = ?
                WHERE pattern_key = ?
            """, (new_count, time.time(), preemptive, pattern_key))

            if preemptive:
                print(f"[MEMORY] Habit detected: {pattern_key} ({new_count}x) → preemptive enabled")
        else:
            # New pattern
            cursor.execute("""
                INSERT INTO habits (pattern_key, count, first_seen, last_seen, emotion)
                VALUES (?, 1, ?, ?, ?)
            """, (pattern_key, time.time(), time.time(), emotion))

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"[MEMORY] Error checking habits: {e}")


def get_preemptive_emotion(hour: int, day_of_week: int) -> str | None:
    """
    Check if there's a preemptive emotion for this time.
    Returns emotion name if a habit is flagged, else None.
    """
    day_type = "Weekend" if day_of_week >= 5 else "Weekday"

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT emotion FROM habits
            WHERE hour_of_day = ? AND day_type = ? AND preemptive_flag = 1
            ORDER BY count DESC LIMIT 1
        """, (hour, day_type))

        row = cursor.fetchone()
        conn.close()

        if row:
            return row["emotion"]
    except Exception as e:
        print(f"[MEMORY] Error getting preemptive: {e}")

    return None


def get_recent_events(limit: int = 10) -> list:
    """Get the most recent events (for debugging)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[MEMORY] Error reading events: {e}")
        return []


# Initialize DB when module is imported
initialize_db()
