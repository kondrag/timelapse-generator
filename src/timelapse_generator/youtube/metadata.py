"""YouTube metadata generation and management."""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from ..config.settings import settings
from ..config.templates import templates
from ..utils.logging import get_logger

logger = get_logger(__name__)


class MetadataManager:
    """Manage YouTube video metadata generation."""

    def __init__(self, templates_dir: Optional[Path] = None):
        """Initialize metadata manager.

        Args:
            templates_dir: Directory containing metadata templates
        """
        self.templates = templates if templates_dir is None else templates.__class__(templates_dir)

    def generate_metadata(
        self,
        video_file: Path,
        kp_index: Optional[float] = None,
        location: Optional[str] = None,
        camera: Optional[str] = None,
        lens: Optional[str] = None,
        fps: Optional[int] = None,
        total_frames: Optional[int] = None,
        duration: Optional[float] = None,
        custom_title: Optional[str] = None,
        custom_description: Optional[str] = None,
        custom_tags: Optional[list] = None,
        thumbnail_path: Optional[Path] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate YouTube metadata for a timelapse video.

        Args:
            video_file: Path to video file
            kp_index: Kp index value (for aurora activity)
            location: Location where video was captured
            camera: Camera used
            lens: Lens used
            fps: Video frame rate
            total_frames: Total number of frames
            duration: Video duration in seconds
            custom_title: Custom title override
            custom_description: Custom description override
            custom_tags: Custom tags override
            **kwargs: Additional metadata fields

        Returns:
            Dictionary with video metadata
        """
        # Use file timestamp as video date
        video_date = datetime.fromtimestamp(video_file.stat().st_mtime)

        # Build context for template rendering
        context = {
            "date": video_date,
            "kp_index": kp_index,
            "location": location,
            "camera": camera,
            "lens": lens,
            "fps": fps,
            "total_frames": total_frames,
            "duration": duration,
            "video_filename": video_file.name,
            "thumbnail_filename": thumbnail_path.name if thumbnail_path else None,
            "has_thumbnail": thumbnail_path is not None,
            **kwargs
        }

        logger.info(f"Generating metadata for {video_file.name}")

        # Generate metadata using templates or custom values
        if custom_title:
            title = custom_title
        else:
            title = self.templates.render_title(context)

        if custom_description:
            description = custom_description
        else:
            description = self.templates.render_description(context)

        if custom_tags:
            tags = custom_tags
        else:
            tags = self.templates.render_tags(context)

        # Add default tags from settings
        default_tags = settings.youtube.tags.copy()
        for tag in default_tags:
            if tag not in tags:
                tags.append(tag)

        metadata = {
            "title": self._sanitize_title(title),
            "description": self._sanitize_description(description),
            "tags": tags,
            "category_id": settings.youtube.category_id,
            "privacy_status": settings.youtube.privacy_status,
            "context": context
        }

        logger.info(f"Generated metadata - Title: {metadata['title'][:50]}...")
        logger.debug(f"Tags: {tags}")

        return metadata

    def _sanitize_title(self, title: str, max_length: int = 100) -> str:
        """Sanitize video title for YouTube.

        Args:
            title: Original title
            max_length: Maximum allowed length

        Returns:
            Sanitized title
        """
        # Remove invalid characters
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        sanitized = title

        for char in invalid_chars:
            sanitized = sanitized.replace(char, '')

        # Trim to maximum length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length-3] + "..."

        return sanitized.strip()

    def _sanitize_description(self, description: str, max_length: int = 5000) -> str:
        """Sanitize video description for YouTube.

        Args:
            description: Original description
            max_length: Maximum allowed length

        Returns:
            Sanitized description
        """
        # Remove excessive whitespace
        lines = description.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]

        # Join lines with appropriate spacing
        sanitized = '\n\n'.join(cleaned_lines)

        # Trim to maximum length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length-3] + "..."

        return sanitized

    def validate_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Validate metadata meets YouTube requirements.

        Args:
            metadata: Metadata dictionary to validate

        Returns:
            Dictionary with validation results
        """
        errors = []
        warnings = []

        # Validate title
        title = metadata.get("title", "")
        if not title:
            errors.append("Title is required")
        elif len(title) > 100:
            errors.append("Title too long (max 100 characters)")
        elif len(title) < 1:
            errors.append("Title too short (min 1 character)")

        # Validate description
        description = metadata.get("description", "")
        if len(description) > 5000:
            errors.append("Description too long (max 5000 characters)")

        # Validate tags
        tags = metadata.get("tags", [])
        if not isinstance(tags, list):
            errors.append("Tags must be a list")
        elif len(tags) > 500:
            errors.append("Too many tags (max 500)")
        else:
            for tag in tags:
                if len(tag) > 30:
                    errors.append(f"Tag too long: {tag[:30]}... (max 30 characters)")
                if len(tag) < 1:
                    warnings.append("Empty tag found")

        # Validate category
        category_id = metadata.get("category_id")
        if category_id and not str(category_id).isdigit():
            errors.append(f"Invalid category ID: {category_id}")

        # Validate privacy status
        privacy_status = metadata.get("privacy_status")
        valid_privacy = ["public", "unlisted", "private"]
        if privacy_status and privacy_status not in valid_privacy:
            errors.append(f"Invalid privacy status: {privacy_status}")

        # Check for recommended practices
        if title and not any(char.isdigit() for char in title):
            warnings.append("Title might benefit from including a date")

        if not description or len(description) < 100:
            warnings.append("Description is short - consider adding more details")

        if len(tags) < 3:
            warnings.append("Consider adding more tags for better discoverability")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "metadata": metadata
        }

    def create_upload_body(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Create YouTube API request body from metadata.

        Args:
            metadata: Metadata dictionary

        Returns:
            Request body for YouTube API
        """
        body = {
            'snippet': {
                'title': metadata.get('title', 'Timelapse Video'),
                'description': metadata.get('description', ''),
                'tags': metadata.get('tags', []),
                'categoryId': metadata.get('category_id', '22')  # People & Blogs
            },
            'status': {
                'privacyStatus': metadata.get('privacy_status', 'private'),
                'selfDeclaredMadeForKids': False
            }
        }

        return body

    def estimate_upload_time(self, file_path: Path) -> Dict[str, Any]:
        """Estimate upload time for a video file.

        Args:
            file_path: Path to video file

        Returns:
            Dictionary with time estimates
        """
        if not file_path.exists():
            return {"error": "File not found"}

        file_size_mb = file_path.stat().st_size / (1024 * 1024)

        # Estimate upload speeds (in Mbps)
        speeds = {
            "slow": 1.0,      # 1 Mbps
            "medium": 5.0,    # 5 Mbps
            "fast": 20.0,     # 20 Mbps
            "very_fast": 50.0  # 50 Mbps
        }

        estimates = {}
        for speed_name, speed_mbps in speeds.items():
            # Convert file size to megabits
            file_size_mbits = file_size_mb * 8
            # Calculate upload time in seconds
            upload_time_seconds = file_size_mbits / speed_mbps
            # Add processing time (rough estimate)
            total_time_seconds = upload_time_seconds * 1.2

            estimates[speed_name] = {
                "upload_speed_mbps": speed_mbps,
                "upload_time_seconds": upload_time_seconds,
                "total_time_seconds": total_time_seconds,
                "upload_time_formatted": self._format_duration(upload_time_seconds),
                "total_time_formatted": self._format_duration(total_time_seconds)
            }

        estimates["file_size_mb"] = file_size_mb
        estimates["file_size_formatted"] = f"{file_size_mb:.1f} MB"

        return estimates

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"