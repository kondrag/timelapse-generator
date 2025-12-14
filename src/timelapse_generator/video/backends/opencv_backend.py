"""
OpenCV-based video encoding backend.

This backend uses OpenCV's VideoWriter for video encoding. It's the most
compatible backend and works on all platforms with minimal dependencies.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging

from .base import VideoBackend

logger = logging.getLogger(__name__)


class OpenCVBackend(VideoBackend):
    """OpenCV-based video encoding backend.

    This backend uses OpenCV's cv2.VideoWriter for video encoding.
    It provides good compatibility and works on all platforms.
    """

    # Backend priority (lower = higher priority)
    priority = 100

    # Video codec mappings
    CODECS = {
        'mp4v': 'mp4v',
        'x264': 'XVID',  # Fallback for OpenCV
        'x265': 'X264',  # Fallback for OpenCV
        'avc1': 'mp4v',
        'h264': 'XVID',
        'hevc': 'X264',
    }

    # Quality presets
    QUALITY_PRESETS = {
        'low': {
            'bitrate': '2M',
            'crf': 28,
            'preset': 'fast',
            'codec': 'mp4v'
        },
        'medium': {
            'bitrate': '5M',
            'crf': 23,
            'preset': 'medium',
            'codec': 'mp4v'
        },
        'high': {
            'bitrate': '10M',
            'crf': 18,
            'preset': 'slow',
            'codec': 'mp4v'
        },
        'ultra': {
            'bitrate': '20M',
            'crf': 15,
            'preset': 'veryslow',
            'codec': 'mp4v'
        }
    }

    def __init__(self,
                 fps: int,
                 width: int,
                 height: int,
                 codec: Optional[str] = None,
                 bitrate: Optional[str] = None,
                 quality_preset: str = 'medium',
                 **kwargs):
        """Initialize the OpenCV backend.

        Args:
            fps: Frames per second for output video
            width: Width of video frames in pixels
            height: Height of video frames in pixels
            codec: Video codec to use
            bitrate: Target bitrate (e.g., '5M', '10M')
            quality_preset: Quality preset ('low', 'medium', 'high', 'ultra')
            **kwargs: Additional OpenCV-specific settings
        """
        self.fps = fps
        self.width = width
        self.height = height
        self.quality_preset = quality_preset.lower()

        # Load quality settings
        if self.quality_preset not in self.QUALITY_PRESETS:
            raise ValueError(f"Invalid quality preset: {quality_preset}. "
                           f"Valid options: {list(self.QUALITY_PRESETS.keys())}")

        settings = self.QUALITY_PRESETS[self.quality_preset].copy()

        # Override with custom settings
        if codec:
            settings['codec'] = codec
        if bitrate:
            settings['bitrate'] = bitrate

        self.codec = settings['codec']
        self.bitrate = settings['bitrate']
        self.crf = settings['crf']
        self.preset = settings['preset']

        # Additional settings from kwargs
        self.use_color_conversion = kwargs.get('use_color_conversion', True)

        self._writer = None
        self._output_path = None
        self._is_opened = False

        # Ensure dimensions are even (required for many codecs)
        self.width, self.height = self._ensure_even_dimensions(width, height)

    @property
    def name(self) -> str:
        """Backend name identifier."""
        return "opencv"

    @property
    def supported_codecs(self) -> List[str]:
        """List of supported video codecs."""
        return list(self.CODECS.keys())

    @property
    def supported_extensions(self) -> List[str]:
        """List of supported output file extensions."""
        return ['.mp4', '.avi', '.mov', '.mkv']

    def get_default_codec(self) -> str:
        """Get the default codec for this backend."""
        return 'mp4v'

    @staticmethod
    def is_available() -> bool:
        """Check if OpenCV is available."""
        try:
            import cv2
            # Test if we can create a VideoWriter
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def open(self, output_path: Path) -> None:
        """Open video writer for the specified output path.

        Args:
            output_path: Path where output video will be written

        Raises:
            RuntimeError: If video writer cannot be initialized
        """
        self._output_path = output_path

        # Get FourCC code
        codec_name = self.CODECS.get(self.codec, self.codec)
        if len(codec_name) != 4:
            raise ValueError(f"Invalid codec name '{codec_name}', must be 4 characters")

        try:
            fourcc = cv2.VideoWriter_fourcc(*codec_name)
        except Exception as e:
            raise RuntimeError(f"Failed to create FourCC codec '{codec_name}': {e}")

        # Create video writer
        self._writer = cv2.VideoWriter(
            str(output_path),
            fourcc,
            self.fps,
            (self.width, self.height)
        )

        if self._writer is None:
            raise RuntimeError(f"Failed to create OpenCV video writer for {output_path}")

        if not self._writer.isOpened():
            self._writer = None
            raise RuntimeError(f"Failed to OpenCV video writer for {output_path}")

        self._is_opened = True
        logger.debug(f"Opened OpenCV video writer: {output_path}")

    def write_frame(self, frame: np.ndarray) -> None:
        """Write a single frame to the video.

        Args:
            frame: Frame data as numpy array (height, width, channels)

        Raises:
            RuntimeError: If video writer is not initialized
            ValueError: If frame has invalid format/dimensions
        """
        if not self._is_opened or self._writer is None:
            raise RuntimeError("Video writer not initialized. Call open() first.")

        # Validate frame format
        if not isinstance(frame, np.ndarray):
            raise ValueError("Frame must be a numpy array")

        if len(frame.shape) != 3:
            raise ValueError(f"Frame must have 3 dimensions, got {len(frame.shape)}")

        if frame.shape[2] not in [1, 3, 4]:
            raise ValueError(f"Frame must have 1, 3, or 4 channels, got {frame.shape[2]}")

        # Ensure frame has correct dimensions
        if frame.shape[:2] != (self.height, self.width):
            logger.debug(f"Resizing frame from {frame.shape[:2]} to ({self.height}, {self.width})")
            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)

        # Convert color format if needed
        if self.use_color_conversion and frame.shape[2] == 3:
            # Ensure frame is in BGR format (OpenCV default)
            # If frame is in RGB, convert to BGR
            # This is a heuristic - ideally we'd know the input format
            pass  # Assume frame is already in correct format

        # Write frame
        success = self._writer.write(frame)
        if not success:
            raise RuntimeError("Failed to write frame to video")

    def close(self) -> None:
        """Close the video writer and finalize the file."""
        if self._writer is not None:
            try:
                self._writer.release()
                logger.debug(f"Closed OpenCV video writer: {self._output_path}")
            except Exception as e:
                logger.warning(f"Error closing video writer: {e}")
            finally:
                self._writer = None
                self._is_opened = False

    def get_encoder_info(self) -> Dict[str, Any]:
        """Get information about the encoder configuration.

        Returns:
            Dictionary containing encoder details and settings
        """
        return {
            'backend': self.name,
            'codec': self.codec,
            'fps': self.fps,
            'resolution': (self.width, self.height),
            'bitrate': self.bitrate,
            'quality_preset': self.quality_preset,
            'crf': self.crf,
            'preset': self.preset,
            'supports_gpu': self.supports_gpu(),
            'pixel_format': self.get_pixel_format(),
            'fourcc': self.CODECS.get(self.codec, self.codec),
        }

    def validate_settings(self) -> List[str]:
        """Validate encoder settings and return list of errors.

        Returns:
            List of error messages. Empty list if all settings are valid.
        """
        errors = []

        if self.fps <= 0:
            errors.append("FPS must be greater than 0")

        if self.fps > 120:
            errors.append("FPS should not exceed 120 for most use cases")

        if self.width <= 0 or self.height <= 0:
            errors.append("Width and height must be greater than 0")

        if self.width > 8192 or self.height > 8192:
            errors.append("Width and height should not exceed 8192 pixels")

        if self.codec not in self.supported_codecs:
            errors.append(f"Unsupported codec: {self.codec}. "
                         f"Supported codecs: {self.supported_codecs}")

        # Check dimensions are even
        if self.width % 2 != 0 or self.height % 2 != 0:
            errors.append("Width and height must be even for most codecs")

        # Check minimum dimensions for some codecs
        if self.codec in ['mp4v', 'x264'] and (self.width < 16 or self.height < 16):
            errors.append("Width and height must be at least 16 pixels for this codec")

        return errors

    def get_pixel_format(self) -> str:
        """Get the pixel format this backend expects.

        Returns:
            Pixel format string ('bgr', 'rgb', 'yuv420p', etc.)
        """
        return 'bgr'  # OpenCV uses BGR format by default

    def supports_gpu(self) -> bool:
        """Check if backend supports GPU acceleration.

        Returns:
            False for standard OpenCV backend
        """
        # Note: OpenCV can use GPU through CUDA modules, but this requires
        # special build and is not commonly available
        return False

    def _ensure_even_dimensions(self, width: int, height: int) -> Tuple[int, int]:
        """Ensure dimensions are even (required for many codecs).

        Args:
            width: Image width
            height: Image height

        Returns:
            Even dimensions (width, height)
        """
        if width % 2 != 0:
            width -= 1
        if height % 2 != 0:
            height -= 1
        return width, height

    def _parse_bitrate(self, bitrate: str) -> int:
        """Parse bitrate string to bits per second.

        Args:
            bitrate: Bitrate string (e.g., '5M', '5000K', '5000000')

        Returns:
            Bitrate in bits per second
        """
        bitrate = bitrate.upper().strip()

        if bitrate.endswith('M'):
            return int(float(bitrate[:-1]) * 1_000_000)
        elif bitrate.endswith('K'):
            return int(float(bitrate[:-1]) * 1_000)
        else:
            return int(bitrate)

    def calculate_output_size(self, frame_count: int) -> int:
        """Calculate estimated output file size in bytes.

        Args:
            frame_count: Number of frames

        Returns:
            Estimated file size in bytes
        """
        duration_seconds = frame_count / self.fps
        bitrate_value = self._parse_bitrate(self.bitrate)
        estimated_bits = bitrate_value * duration_seconds
        return estimated_bits // 8  # Convert to bytes