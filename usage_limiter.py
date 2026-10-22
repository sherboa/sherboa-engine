# This module tracks per-IP analysis usage with a rolling 24-hour quota using persistent SQLite storage.

import math
import os
import sqlite3
import time
from pathlib import Path

########################################################################################################################
# CONSTANTS
########################################################################################################################
USAGE_LIMIT_WINDOW_SECONDS = 24 * 60 * 60  # Rolling window in which each client's analysis starts are counted
USAGE_LIMIT_MAX_ANALYSES = 20  # Maximum number of analyses an IP can start within the rolling window
USAGE_DB_PATH = os.getenv("SHERBOA_USAGE_DB_PATH", "/data/usage.db")  # Persistent SQLite location; can be overridden for local tests
SQLITE_BUSY_TIMEOUT_SECONDS = 5  # Maximum time SQLite waits for another transaction to release its lock


########################################################################################################################
# USAGE LIMIT EXCEPTION
########################################################################################################################
class UsageLimitExceeded(Exception):
    """
    Raised when an IP has exhausted its rolling analysis quota.
    """

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("the daily analysis limit has been reached.")


########################################################################################################################
# USAGE LIMITER
########################################################################################################################
class UsageLimiter:
    """
    Track analysis starts per IP using a persistent SQLite database.
    """

    def __init__(self, db_path: str = USAGE_DB_PATH):
        self.db_path = str(db_path)

        # Create the parent directory when it does not already exist; in production, the mounted /data directory must be writable by the sherboa-user account (UID 10001)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        """
        Open a database connection with a bounded lock wait.
        """
        return sqlite3.connect(
            self.db_path,
            timeout=SQLITE_BUSY_TIMEOUT_SECONDS,
        )

    def _initialize_database(self) -> None:
        """
        Create the usage table and index if they do not exist.
        """
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_usage (
                    id INTEGER PRIMARY KEY,
                    client_ip TEXT NOT NULL,
                    started_at REAL NOT NULL
                )
                """
            )

            # This index speeds up counting recent analyses for one IP
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_analysis_usage_ip_time
                ON analysis_usage (client_ip, started_at)
                """
            )

    def register_analysis(self, client_ip: str) -> None:
        """
        Atomically reserve one analysis for an IP.

        Raises UsageLimitExceeded when the IP has reached its quota.
        Rejected attempts are not recorded.
        """
        now = time.time()

        # Anything at or before this timestamp is outside the 24-hour window
        cutoff = now - USAGE_LIMIT_WINDOW_SECONDS

        with self._connect() as connection:
            # Acquire the write reservation before checking the count; this serializes quota checks across concurrent DB connections, preventing simultaneous requests from exceeding the limit
            connection.execute("BEGIN IMMEDIATE")

            # Delete expired records to keep the database from growing forever; this cleanup does not affect any records inside the active window
            connection.execute(
                "DELETE FROM analysis_usage WHERE started_at <= ?",
                (cutoff,),
            )

            row = connection.execute(
                """
                SELECT COUNT(*), MIN(started_at)
                FROM analysis_usage
                WHERE client_ip = ? AND started_at > ?
                """,
                (client_ip, cutoff),
            ).fetchone()

            count, oldest_timestamp = row

            if count >= USAGE_LIMIT_MAX_ANALYSES:
                # The oldest active record determines when this IP gets its next available slot in the rolling window
                retry_after = max(
                    1,
                    math.ceil(
                        oldest_timestamp
                        + USAGE_LIMIT_WINDOW_SECONDS
                        - now
                    ),
                )

                # Commit the expired-record cleanup, but do not record this rejected attempt as a consumed analysis
                connection.commit()
                raise UsageLimitExceeded(retry_after)

            # Reserve the quota immediately before actual video processing; once registered, the analysis counts even if processing fails
            connection.execute(
                """
                INSERT INTO analysis_usage (client_ip, started_at)
                VALUES (?, ?)
                """,
                (client_ip, now),
            )
            connection.commit()
