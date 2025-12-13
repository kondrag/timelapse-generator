"""Configuration settings for the timelapse generator application."""

import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator


class VideoSettings(BaseModel):
    """Video generation settings."""

    output_path: Path = Field(default=Path("./output"), description="Output directory for videos")
    fps: int = Field(default=30, ge=1, le=120, description="Frames per second")
    quality: str = Field(default="medium", pattern="^(low|medium|high|custom)$", description="Video quality preset")
    codec: str = Field(default="mp4v", description="Video codec")
    bitrate: Optional[str] = Field(default=None, description="Custom bitrate (e.g., '5M', '10M')")
    resolution: Optional[tuple[int, int]] = Field(default=None, description="Output resolution (width, height)")

    @property
    def quality_settings(self) -> Dict[str, str]:
        """Get quality preset settings."""
        presets = {
            "low": {"bitrate": "2M", "codec": "mp4v"},
            "medium": {"bitrate": "5M", "codec": "mp4v"},
            "high": {"bitrate": "10M", "codec": "mp4v"},
            "custom": {"bitrate": self.bitrate or "5M", "codec": self.codec}
        }
        return presets[self.quality]


class WeatherSettings(BaseModel):
    """Weather and Kp index monitoring settings."""

    noaa_url: str = Field(
        default="https://www.swpc.noaa.gov/products/solar-and-geophysical-activity-summary",
        description="NOAA SpaceWeather summary URL"
    )
    kp_threshold: int = Field(default=4, ge=0, le=9, description="Kp index threshold for upload")
    cache_duration: int = Field(default=3600, ge=60, description="Cache duration in seconds")
    retry_attempts: int = Field(default=3, ge=1, le=10, description="Number of retry attempts")
    retry_delay: int = Field(default=5, ge=1, le=60, description="Delay between retries in seconds")


class YouTubeSettings(BaseModel):
    """YouTube upload settings."""

    upload_enabled: bool = Field(default=False, description="Enable YouTube uploads")
    privacy_status: str = Field(
        default="private",
        pattern="^(public|unlisted|private)$",
        description="Video privacy status"
    )
    category_id: str = Field(default="22", description="YouTube video category ID")
    tags: List[str] = Field(default_factory=lambda: ["timelapse", "astrophotography", "night sky"], description="Default video tags")

    @validator('category_id')
    def validate_category_id(cls, v):
        """Validate YouTube category ID."""
        valid_categories = {
            "1": "Film & Animation",
            "2": "Autos & Vehicles",
            "10": "Music",
            "15": "Pets & Animals",
            "17": "Sports",
            "19": "Travel & Events",
            "20": "Gaming",
            "22": "People & Blogs",
            "23": "Comedy",
            "24": "Entertainment",
            "25": "News & Politics",
            "26": "Howto & Style",
            "27": "Education",
            "28": "Science & Technology",
            "29": "Nonprofits & Activism"
        }
        if v not in valid_categories:
            raise ValueError(f"Invalid category ID. Valid IDs: {list(valid_categories.keys())}")
        return v


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$", description="Log level")
    file_path: Optional[Path] = Field(default=None, description="Log file path")
    max_file_size: int = Field(default=10_485_760, description="Maximum log file size in bytes")  # 10MB
    backup_count: int = Field(default=5, description="Number of log file backups")


class Settings(BaseModel):
    """Main application settings."""

    video: VideoSettings = Field(default_factory=VideoSettings)
    weather: WeatherSettings = Field(default_factory=WeatherSettings)
    youtube: YouTubeSettings = Field(default_factory=YouTubeSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @classmethod
    def from_file(cls, config_path: Optional[Path] = None) -> "Settings":
        """Load settings from configuration file."""
        if config_path is None:
            config_path = Path("config.yaml")

        if not config_path.exists():
            # Create default config file
            settings = cls()
            settings.save_to_file(config_path)
            return settings

        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)

        return cls(**config_data)

    def save_to_file(self, config_path: Path) -> None:
        """Save settings to configuration file."""
        config_data = self.dict()

        # Convert Path objects to strings for YAML serialization
        def convert_paths(obj):
            if isinstance(obj, dict):
                return {k: convert_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_paths(item) for item in obj]
            elif isinstance(obj, Path):
                return str(obj)
            else:
                return obj

        config_data = convert_paths(config_data)

        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False, indent=2)

    @classmethod
    def load_with_env(cls, config_path: Optional[Path] = None) -> "Settings":
        """Load settings from file and environment variables."""
        # Load environment variables from .env file if it exists
        load_dotenv()

        settings = cls.from_file(config_path)

        # Override with environment variables if present
        if os.getenv("YOUTUBE_UPLOAD_ENABLED"):
            settings.youtube.upload_enabled = os.getenv("YOUTUBE_UPLOAD_ENABLED").lower() == "true"

        if os.getenv("KP_THRESHOLD"):
            settings.weather.kp_threshold = int(os.getenv("KP_THRESHOLD"))

        return settings


# Global settings instance
settings = Settings.load_with_env()