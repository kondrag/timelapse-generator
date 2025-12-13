"""NOAA SpaceWeather client for fetching Kp index data."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from bs4 import BeautifulSoup

from ..config.settings import settings
from ..utils.logging import get_logger
from ..utils.retry import retry

logger = get_logger(__name__)


class NOAAClient:
    """Client for fetching NOAA SpaceWeather data."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize NOAA client.

        Args:
            cache_dir: Directory for caching responses
        """
        self.base_url = settings.weather.noaa_url
        self.cache_dir = cache_dir or Path.home() / ".cache" / "timelapse_generator"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "noaa_cache.json"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; TimelapseGenerator/1.0; +https://github.com/example/timelapse-generator)'
        })

    @retry((requests.RequestException, ConnectionError), max_attempts=3, delay=2.0)
    def fetch_summary_page(self) -> str:
        """Fetch the NOAA SpaceWeather summary page.

        Returns:
            HTML content of the page

        Raises:
            requests.RequestException: If request fails
        """
        logger.info(f"Fetching NOAA summary page: {self.base_url}")

        try:
            response = self.session.get(
                self.base_url,
                timeout=30,
                headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
            )
            response.raise_for_status()
            return response.text

        except requests.RequestException as e:
            logger.error(f"Failed to fetch NOAA page: {e}")
            raise

    def parse_kp_data(self, html_content: str) -> Dict[str, Any]:
        """Parse Kp index data from NOAA HTML content.

        Args:
            html_content: HTML content from NOAA website

        Returns:
            Dictionary with parsed Kp data
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        kp_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "source_url": self.base_url,
            "data": {}
        }

        try:
            # Look for tables containing Kp index data
            tables = soup.find_all('table')
            kp_table = None

            for table in tables:
                # Look for table headers that suggest Kp index data
                headers = table.find_all(['th', 'td'])
                header_text = ' '.join([h.get_text().strip().lower() for h in headers])

                if 'kp' in header_text and any(word in header_text for word in ['index', 'geomagnetic', 'activity']):
                    kp_table = table
                    break

            if not kp_table:
                logger.warning("Could not find Kp index table, trying alternative parsing")
                return self._fallback_parse_kp_data(html_content)

            # Extract Kp index values
            rows = kp_table.find_all('tr')
            kp_values = []

            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:  # Need at least time and Kp value
                    try:
                        # Try to extract numeric Kp values from cells
                        row_text = [cell.get_text().strip() for cell in cells]
                        kp_numbers = []

                        for cell in cells:
                            text = cell.get_text().strip()
                            # Look for numeric Kp values (0-9, possibly with decimals)
                            import re
                            matches = re.findall(r'\d+\.?\d*', text)
                            kp_numbers.extend([float(m) for m in matches])

                        # Filter reasonable Kp values (0-9)
                        kp_values.extend([v for v in kp_numbers if 0 <= v <= 9])

                    except (ValueError, IndexError) as e:
                        logger.debug(f"Could not parse row: {e}")
                        continue

            if kp_values:
                # Calculate statistics
                latest_kp = kp_values[-1] if kp_values else None
                max_kp = max(kp_values)
                avg_kp = sum(kp_values) / len(kp_values)

                kp_data["data"] = {
                    "latest_kp": latest_kp,
                    "max_kp": max_kp,
                    "average_kp": avg_kp,
                    "kp_values": kp_values[-24:],  # Keep last 24 values
                    "value_count": len(kp_values),
                    "status": "success"
                }

                logger.info(f"Successfully parsed Kp data: latest={latest_kp}, max={max_kp}, avg={avg_kp:.1f}")
            else:
                kp_data["data"] = {
                    "status": "no_data",
                    "message": "No Kp values found in parsed data"
                }
                logger.warning("No Kp values found in parsed data")

        except Exception as e:
            logger.error(f"Error parsing Kp data: {e}")
            kp_data["data"] = {
                "status": "parse_error",
                "message": str(e)
            }

        return kp_data

    def _fallback_parse_kp_data(self, html_content: str) -> Dict[str, Any]:
        """Fallback parsing method for Kp data.

        Args:
            html_content: HTML content from NOAA website

        Returns:
            Dictionary with parsed Kp data
        """
        logger.info("Using fallback Kp parsing method")

        soup = BeautifulSoup(html_content, 'html.parser')
        text_content = soup.get_text()

        # Look for Kp index mentions in text
        import re
        kp_patterns = [
            r'Kp\s*=\s*(\d+\.?\d*)',
            r'Kp\s*index\s*:?\s*(\d+\.?\d*)',
            r'Kp\s*(\d+\.?\d*)',
        ]

        kp_values = []
        for pattern in kp_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE)
            kp_values.extend([float(m) for m in matches if 0 <= float(m) <= 9])

        if kp_values:
            latest_kp = kp_values[-1]
            max_kp = max(kp_values)
            avg_kp = sum(kp_values) / len(kp_values)

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "source_url": self.base_url,
                "data": {
                    "latest_kp": latest_kp,
                    "max_kp": max_kp,
                    "average_kp": avg_kp,
                    "kp_values": kp_values,
                    "value_count": len(kp_values),
                    "status": "success",
                    "parsing_method": "fallback"
                }
            }
        else:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "source_url": self.base_url,
                "data": {
                    "status": "no_data",
                    "message": "No Kp values found with fallback parsing",
                    "parsing_method": "fallback"
                }
            }

    def get_cached_data(self, max_age_minutes: int = 60) -> Optional[Dict[str, Any]]:
        """Get cached Kp data if available and not too old.

        Args:
            max_age_minutes: Maximum age of cached data in minutes

        Returns:
            Cached data or None if not available/expired
        """
        if not self.cache_file.exists():
            return None

        try:
            with open(self.cache_file, 'r') as f:
                cached_data = json.load(f)

            # Check age
            cache_time = datetime.fromisoformat(cached_data.get("timestamp", ""))
            age = datetime.utcnow() - cache_time

            if age > timedelta(minutes=max_age_minutes):
                logger.info(f"Cached data is {age.total_seconds()/60:.1f} minutes old, refreshing")
                return None

            logger.info(f"Using cached data from {age.total_seconds()/60:.1f} minutes ago")
            return cached_data

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Error reading cache file: {e}")
            return None

    def save_cached_data(self, data: Dict[str, Any]) -> None:
        """Save Kp data to cache.

        Args:
            data: Data to cache
        """
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.debug(f"Saved data to cache: {self.cache_file}")

        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def get_kp_index(self, use_cache: bool = True) -> Dict[str, Any]:
        """Get current Kp index from NOAA.

        Args:
            use_cache: Whether to use cached data if available

        Returns:
            Dictionary with Kp index data
        """
        logger.info("Fetching Kp index data")

        # Check cache first
        if use_cache:
            cached_data = self.get_cached_data(settings.weather.cache_duration // 60)
            if cached_data and cached_data.get("data", {}).get("status") == "success":
                return cached_data

        try:
            # Fetch fresh data
            html_content = self.fetch_summary_page()
            kp_data = self.parse_kp_data(html_content)

            # Save to cache if successful
            if kp_data.get("data", {}).get("status") == "success":
                self.save_cached_data(kp_data)

            return kp_data

        except Exception as e:
            logger.error(f"Failed to get Kp index: {e}")
            # Return cached data as fallback
            cached_data = self.get_cached_data(24 * 60)  # Accept older cache as fallback
            if cached_data:
                logger.warning("Using cached data as fallback due to fetch failure")
                return cached_data

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "source_url": self.base_url,
                "data": {
                    "status": "error",
                    "message": str(e)
                }
            }

    def check_kp_threshold(self, threshold: Optional[int] = None) -> Dict[str, Any]:
        """Check if Kp index meets or exceeds threshold.

        Args:
            threshold: Kp threshold to check (uses settings default if None)

        Returns:
            Dictionary with threshold check results
        """
        if threshold is None:
            threshold = settings.weather.kp_threshold

        logger.info(f"Checking Kp index against threshold {threshold}")

        kp_data = self.get_kp_index()
        kp_status = kp_data.get("data", {})

        if kp_status.get("status") != "success":
            return {
                "threshold_met": False,
                "threshold": threshold,
                "kp_data": kp_data,
                "message": "Could not determine Kp index"
            }

        latest_kp = kp_status.get("latest_kp")
        max_kp = kp_status.get("max_kp")

        threshold_met = max_kp >= threshold if max_kp is not None else False

        result = {
            "threshold_met": threshold_met,
            "threshold": threshold,
            "latest_kp": latest_kp,
            "max_kp": max_kp,
            "average_kp": kp_status.get("average_kp"),
            "kp_data": kp_data,
            "timestamp": kp_data.get("timestamp")
        }

        if threshold_met:
            logger.info(f"Kp threshold met: max Kp = {max_kp} >= {threshold}")
        else:
            logger.info(f"Kp threshold not met: max Kp = {max_kp} < {threshold}")

        return result