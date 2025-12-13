"""Kp index parsing utilities and historical data management."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..utils.logging import get_logger

logger = get_logger(__name__)


class KpIndexParser:
    """Parse and manage Kp index historical data."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize Kp index parser.

        Args:
            db_path: Path to SQLite database for historical data
        """
        if db_path is None:
            db_path = Path.home() / ".cache" / "timelapse_generator" / "kp_data.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the SQLite database for Kp data."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS kp_observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        kp_value REAL NOT NULL,
                        source TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp
                    ON kp_observations(timestamp)
                """)

                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_created_at
                    ON kp_observations(created_at)
                """)

                conn.commit()
                logger.debug("Database initialized successfully")

        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def store_kp_observation(self, timestamp: datetime, kp_value: float, source: str = "noaa") -> None:
        """Store a Kp index observation.

        Args:
            timestamp: Observation timestamp
            kp_value: Kp index value
            source: Data source
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "INSERT INTO kp_observations (timestamp, kp_value, source) VALUES (?, ?, ?)",
                    (timestamp.isoformat(), kp_value, source)
                )
                conn.commit()
                logger.debug(f"Stored Kp observation: {timestamp.isoformat()}, Kp={kp_value}")

        except sqlite3.Error as e:
            logger.error(f"Failed to store Kp observation: {e}")

    def store_kp_series(self, kp_data: Dict[str, Any]) -> None:
        """Store a series of Kp observations.

        Args:
            kp_data: Dictionary containing Kp observations from NOAA client
        """
        data = kp_data.get("data", {})
        if data.get("status") != "success" or not data.get("kp_values"):
            logger.warning("No valid Kp data to store")
            return

        timestamp = datetime.fromisoformat(kp_data.get("timestamp", datetime.utcnow().isoformat()))
        kp_values = data.get("kp_values", [])

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                for i, kp_value in enumerate(kp_values[-24:]):  # Store last 24 values
                    obs_time = timestamp - timedelta(hours=len(kp_values)-24+i)
                    self.store_kp_observation(obs_time, kp_value, "noaa")

                conn.commit()
                logger.info(f"Stored {len(kp_values[-24:])} Kp observations")

        except sqlite3.Error as e:
            logger.error(f"Failed to store Kp series: {e}")

    def get_kp_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get Kp index history.

        Args:
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of observations to return

        Returns:
            List of Kp observations
        """
        if end_time is None:
            end_time = datetime.utcnow()
        if start_time is None:
            start_time = end_time - timedelta(days=1)

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row

                query = """
                    SELECT timestamp, kp_value, source, created_at
                    FROM kp_observations
                    WHERE timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp DESC
                """

                params = [start_time.isoformat(), end_time.isoformat()]

                if limit:
                    query += " LIMIT ?"
                    params.append(limit)

                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Failed to get Kp history: {e}")
            return []

    def get_overnight_kp_max(self, night_start_hour: int = 20, night_end_hour: int = 6) -> Optional[Dict[str, Any]]:
        """Get maximum Kp index for the previous night.

        Args:
            night_start_hour: Hour when night starts (20 = 8 PM)
            night_end_hour: Hour when night ends (6 = 6 AM)

        Returns:
            Dictionary with overnight Kp statistics or None if no data
        """
        now = datetime.utcnow()

        # Determine night period
        if now.hour >= night_start_hour:
            # We're in tonight's night period
            night_start = now.replace(hour=night_start_hour, minute=0, second=0, microsecond=0)
            night_end = (night_start + timedelta(hours=(24 - night_start_hour) + night_end_hour))
        elif now.hour < night_end_hour:
            # We're in tonight's early morning
            night_start = (now - timedelta(days=1)).replace(hour=night_start_hour, minute=0, second=0, microsecond=0)
            night_end = now.replace(hour=night_end_hour, minute=0, second=0, microsecond=0)
        else:
            # We're in between, use last night
            night_start = (now - timedelta(days=1)).replace(hour=night_start_hour, minute=0, second=0, microsecond=0)
            night_end = now.replace(hour=night_end_hour, minute=0, second=0, microsecond=0)

        logger.info(f"Checking Kp for night period: {night_start} to {night_end}")

        observations = self.get_kp_history(night_start, night_end)

        if not observations:
            logger.warning("No Kp observations found for night period")
            return None

        kp_values = [obs["kp_value"] for obs in observations]
        max_kp = max(kp_values)
        avg_kp = sum(kp_values) / len(kp_values)

        result = {
            "night_start": night_start.isoformat(),
            "night_end": night_end.isoformat(),
            "max_kp": max_kp,
            "average_kp": avg_kp,
            "observation_count": len(observations),
            "observations": observations,
            "timestamp": now.isoformat()
        }

        logger.info(f"Overnight Kp stats: max={max_kp}, avg={avg_kp:.1f}, observations={len(observations)}")
        return result

    def check_overnight_threshold(self, threshold: int, night_start_hour: int = 20, night_end_hour: int = 6) -> Dict[str, Any]:
        """Check if overnight Kp index met threshold.

        Args:
            threshold: Kp threshold to check
            night_start_hour: Hour when night starts
            night_end_hour: Hour when night ends

        Returns:
            Dictionary with threshold check results
        """
        overnight_stats = self.get_overnight_kp_max(night_start_hour, night_end_hour)

        if overnight_stats is None:
            return {
                "threshold_met": False,
                "threshold": threshold,
                "message": "No overnight Kp data available",
                "night_start": (datetime.utcnow() - timedelta(days=1)).replace(hour=20, minute=0, second=0).isoformat(),
                "night_end": datetime.utcnow().replace(hour=6, minute=0, second=0).isoformat()
            }

        max_kp = overnight_stats["max_kp"]
        threshold_met = max_kp >= threshold

        result = {
            "threshold_met": threshold_met,
            "threshold": threshold,
            "max_kp": max_kp,
            "average_kp": overnight_stats["average_kp"],
            "night_start": overnight_stats["night_start"],
            "night_end": overnight_stats["night_end"],
            "observation_count": overnight_stats["observation_count"],
            "timestamp": overnight_stats["timestamp"]
        }

        if threshold_met:
            logger.info(f"Overnight Kp threshold {threshold} met: max Kp = {max_kp}")
        else:
            logger.info(f"Overnight Kp threshold {threshold} not met: max Kp = {max_kp}")

        return result

    def cleanup_old_data(self, days_to_keep: int = 30) -> None:
        """Clean up old Kp observations.

        Args:
            days_to_keep: Number of days to keep data for
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.execute(
                    "DELETE FROM kp_observations WHERE timestamp < ?",
                    (cutoff_date.isoformat(),)
                )
                deleted_count = cursor.rowcount
                conn.commit()

                logger.info(f"Cleaned up {deleted_count} old Kp observations")

        except sqlite3.Error as e:
            logger.error(f"Failed to cleanup old data: {e}")

    def export_data(self, output_path: Path, format: str = "json") -> None:
        """Export Kp data to file.

        Args:
            output_path: Output file path
            format: Export format ('json' or 'csv')
        """
        observations = self.get_kp_history(limit=1000)  # Get recent data

        if format.lower() == "json":
            output_path.write_text(json.dumps(observations, indent=2, default=str))
        elif format.lower() == "csv":
            import csv
            with open(output_path, 'w', newline='') as csvfile:
                if observations:
                    writer = csv.DictWriter(csvfile, fieldnames=observations[0].keys())
                    writer.writeheader()
                    writer.writerows(observations)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        logger.info(f"Exported {len(observations)} observations to {output_path}")