"""
Abstract base class for video encoding backends.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import numpy as np


class VideoBackend(ABC):
    """Abstract base class for video encoding backends.

    This class defines the interface that all video backends must implement.
    It provides a consistent API for video generation regardless of the
    underlying encoding technology.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name identifier."""
        pass

    @property
    @abstractmethod
    def supported_codecs(self) -> List[str]:
        """List of supported video codecs."""
        pass

    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """List of supported output file extensions."""
        pass

    @abstractmethod
    def get_default_codec(self) -> str:
        """Get the default codec for this backend."""
        pass

    @abstractmethod
    def __init__(self,
                 fps: int,
                 width: int,
                 height: int,
                 codec: Optional[str] = None,
                 bitrate: Optional[str] = None,
                 quality_preset: str = 'medium',
                 **kwargs):
        """Initialize the video backend.

        Args:
            fps: Frames per second for output video
            width: Width of video frames in pixels
            height: Height of video frames in pixels
            codec: Video codec to use (e.g., 'h264', 'libx264')
            bitrate: Target bitrate (e.g., '5M', '10M')
            quality_preset: Quality preset ('low', 'medium', 'high', 'ultra')
            **kwargs: Backend-specific configuration options
        """
        pass

    @abstractmethod
    def open(self, output_path: Path) -> None:
        """Open video writer for the specified output path.

        Args:
            output_path: Path where output video will be written

        Raises:
            RuntimeError: If video writer cannot be initialized
        """
        pass

    @abstractmethod
    def write_frame(self, frame: np.ndarray) -> None:
        """Write a single frame to the video.

        Args:
            frame: Frame data as numpy array (height, width, channels)

        Raises:
            RuntimeError: If video writer is not initialized
            ValueError: If frame has invalid format/dimensions
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the video writer and finalize the file."""
        pass

    @abstractmethod
    def get_encoder_info(self) -> Dict[str, Any]:
        """Get information about the encoder configuration.

        Returns:
            Dictionary containing encoder details and settings
        """
        pass

    @abstractmethod
    def validate_settings(self) -> List[str]:
        """Validate encoder settings and return list of errors.

        Returns:
            List of error messages. Empty list if all settings are valid.
        """
        pass

    @staticmethod
    @abstractmethod
    def is_available() -> bool:
        """Check if this backend is available (dependencies installed).

        Returns:
            True if backend can be used, False otherwise
        """
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def get_pixel_format(self) -> str:
        """Get the pixel format this backend expects.

        Returns:
            Pixel format string ('bgr', 'rgb', 'yuv420p', etc.)
        """
        return 'bgr'  # Default for OpenCV compatibility

    def supports_gpu(self) -> bool:
        """Check if backend supports GPU acceleration.

        Returns:
            True if backend can use GPU acceleration
        """
        return False

    def get_recommended_bitrate(self, resolution: Tuple[int, int], fps: int, quality: str) -> str:
        """Get recommended bitrate based on resolution, fps, and quality.

        Args:
            resolution: (width, height) tuple
            fps: Frames per second
            quality: Quality level ('low', 'medium', 'high', 'ultra')

        Returns:
            Recommended bitrate string (e.g., '5M')
        """
        # Basic bitrate calculation
        megapixels = (resolution[0] * resolution[1]) / 1000000

        # Base bitrate per megapixel at 30fps
        base_bitrates = {
            'low': 2,
            'medium': 5,
            'high': 10,
            'ultra': 20
        }

        # Scale based on fps and resolution
        base = base_bitrates.get(quality, 5)
        fps_factor = fps / 30
        resolution_factor = max(megapixels / 2.0, 0.5)  # Scale for resolution

        bitrate_mbps = base * fps_factor * resolution_factor
        return f"{int(bitrate_mbps)}M"