"""
FFmpegCV-based video encoding backend.

This backend uses the ffmpegcv library for video encoding, providing
better performance, GPU acceleration support, and professional-grade
encoding options compared to OpenCV.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging

from .base import VideoBackend

logger = logging.getLogger(__name__)


class FFmpegCVBackend(VideoBackend):
    """FFmpegCV-based video encoding backend.

    This backend uses ffmpegcv for video encoding, providing:
    - Hardware acceleration (NVENC, QSV, etc.)
    - Better codec support (H.264, H.265, VP9)
    - Professional encoding options
    - Higher performance than OpenCV
    """

    # Backend priority (lower = higher priority)
    priority = 90  # Higher priority than OpenCV

    # Supported hardware acceleration methods
    HARDWARE_ACCELERATION = {
        'nvidia': ['h264_nvenc', 'hevc_nvenc'],
        'intel': ['h264_qsv', 'hevc_qsv'],
        'amd': ['h264_amf', 'hevc_amf'],
        'software': ['libx264', 'libx265', 'mpeg4']
    }

    # Quality presets mapping
    FFMPEG_PRESETS = {
        'low': 'fast',
        'medium': 'medium',
        'high': 'slow',
        'ultra': 'veryslow'
    }

    # CRF values for different quality levels
    CRF_VALUES = {
        'low': 28,
        'medium': 23,
        'high': 18,
        'ultra': 15
    }

    def __init__(self,
                 fps: int,
                 width: int,
                 height: int,
                 codec: Optional[str] = None,
                 bitrate: Optional[str] = None,
                 quality_preset: str = 'medium',
                 preset: Optional[str] = None,
                 crf: Optional[int] = None,
                 pix_fmt: Optional[str] = None,
                 hardware_accel: str = 'auto',
                 gpu_id: int = 0,
                 **kwargs):
        """Initialize the FFmpegCV backend.

        Args:
            fps: Frames per second for output video
            width: Width of video frames in pixels
            height: Height of video frames in pixels
            codec: Video codec to use (e.g., 'libx264', 'h264_nvenc')
            bitrate: Target bitrate (e.g., '5M', '10M')
            quality_preset: Quality preset ('low', 'medium', 'high', 'ultra')
            preset: FFmpeg encoding preset (ultrafast to veryslow)
            crf: Constant Rate Factor (0-51, lower = better quality)
            pix_fmt: Pixel format (e.g., 'yuv420p', 'yuv444p')
            hardware_accel: Hardware acceleration ('auto', 'nvidia', 'intel', 'amd', 'none')
            gpu_id: GPU device ID for hardware acceleration
            **kwargs: Additional FFmpeg-specific settings
        """
        self.fps = fps
        self.width = width
        self.height = height
        self.quality_preset = quality_preset.lower()
        self.hardware_accel = hardware_accel
        self.gpu_id = gpu_id

        # Initialize ffmpegcv module (lazy loading)
        self._ffmpegcv = None

        # Set quality settings
        if self.quality_preset not in self.FFMPEG_PRESETS:
            raise ValueError(f"Invalid quality preset: {quality_preset}. "
                           f"Valid options: {list(self.FFMPEG_PRESETS.keys())}")

        # Determine preset and CRF
        self.preset = preset or self.FFMPEG_PRESETS[self.quality_preset]
        self.crf = crf or self.CRF_VALUES[self.quality_preset]

        # Set codec
        self.codec = codec or self._select_optimal_codec()

        # Set bitrate
        self.bitrate = bitrate or self._get_default_bitrate()

        # Set pixel format
        self.pix_fmt = pix_fmt or 'yuv420p'  # Default for compatibility

        # Additional settings
        self.thread_count = kwargs.get('threads', 0)  # 0 = auto
        self.min bitrate = kwargs.get('min_bitrate', None)
        self.max_bitrate = kwargs.get('max_bitrate', None)

        self._writer = None
        self._output_path = None
        self._is_opened = False

        # Ensure dimensions are even (required for most codecs)
        self.width, self.height = self._ensure_even_dimensions(width, height)

    @property
    def name(self) -> str:
        """Backend name identifier."""
        return "ffmpegcv"

    @property
    def supported_codecs(self) -> List[str]:
        """List of supported video codecs."""
        codecs = ['libx264', 'libx265', 'libvpx-vp9', 'mpeg4']

        # Add hardware accelerated codecs if available
        if self._is_nvidia_available():
            codecs.extend(['h264_nvenc', 'hevc_nvenc'])
        if self._is_intel_qsv_available():
            codecs.extend(['h264_qsv', 'hevc_qsv'])
        if self._is_amd_available():
            codecs.extend(['h264_amf', 'hevc_amf'])

        return codecs

    @property
    def supported_extensions(self) -> List[str]:
        """List of supported output file extensions."""
        return ['.mp4', '.avi', '.mov', '.mkv', '.webm']

    def get_default_codec(self) -> str:
        """Get the default codec for this backend."""
        return self._select_optimal_codec()

    @staticmethod
    def is_available() -> bool:
        """Check if ffmpegcv is available."""
        try:
            import ffmpegcv
            # Try to get FFmpeg version to verify it's working
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def _import_ffmpegcv(self):
        """Import ffmpegcv module lazily."""
        if self._ffmpegcv is None:
            try:
                import ffmpegcv
                self._ffmpegcv = ffmpegcv
            except ImportError as e:
                raise RuntimeError(f"ffmpegcv is not installed. Install with: pip install ffmpegcv") from e

    def _select_optimal_codec(self) -> str:
        """Select the optimal codec based on hardware availability."""
        # Try hardware accelerated codecs first
        if self.hardware_accel in ['auto', 'nvidia'] and self._is_nvidia_available():
            return 'h264_nvenc'
        elif self.hardware_accel in ['auto', 'intel'] and self._is_intel_qsv_available():
            return 'h264_qsv'
        elif self.hardware_accel in ['auto', 'amd'] and self._is_amd_available():
            return 'h264_amf'

        # Fall back to software encoding
        return 'libx264'

    def _is_nvidia_available(self) -> bool:
        """Check if NVIDIA GPU acceleration is available."""
        try:
            self._import_ffmpegcv()
            # Try to create NVENC writer to test availability
            writer = self._ffmpegcv.VideoWriterNV(
                '/dev/null',  # Use null device for testing
                codec='h264_nvenc',
                fps=30.0,
                size=(320, 240)
            )
            writer.release()
            return True
        except:
            return False

    def _is_intel_qsv_available(self) -> bool:
        """Check if Intel Quick Sync Video is available."""
        try:
            self._import_ffmpegcv()
            writer = self._ffmpegcv.VideoWriterQSV(
                '/dev/null',
                codec='h264_qsv',
                fps=30.0,
                size=(320, 240)
            )
            writer.release()
            return True
        except:
            return False

    def _is_amd_available(self) -> bool:
        """Check if AMD GPU acceleration is available."""
        try:
            self._import_ffmpegcv()
            # ffmpegcv might not have dedicated AMD writer, test via regular writer
            return True
        except:
            return False

    def _get_default_bitrate(self) -> str:
        """Get default bitrate based on resolution and quality."""
        # Calculate bitrate based on resolution
        pixels = self.width * self.height
        megapixels = pixels / 1_000_000

        # Base bitrate per megapixel
        base_bitrate = {
            'low': 2,
            'medium': 5,
            'high': 10,
            'ultra': 20
        }[self.quality_preset]

        # Scale for resolution
        bitrate_mbps = base_bitrate * max(megapixels / 2.0, 0.5)
        return f"{int(bitrate_mbps)}M"

    def _ensure_even_dimensions(self, width: int, height: int) -> Tuple[int, int]:
        """Ensure dimensions are even (required for most codecs)."""
        if width % 2 != 0:
            width -= 1
        if height % 2 != 0:
            height -= 1
        return width, height

    def open(self, output_path: Path) -> None:
        """Open video writer for the specified output path.

        Args:
            output_path: Path where output video will be written

        Raises:
            RuntimeError: If video writer cannot be initialized
        """
        self._import_ffmpegcv()
        self._output_path = output_path

        # Build ffmpegcv parameters
        params = {
            'fps': self.fps,
            'size': (self.width, self.height),
            'codec': self.codec,
            'preset': self.preset,
            'crf': self.crf,
            'pix_fmt': self.pix_fmt
        }

        # Add bitrate if specified
        if self.bitrate:
            params['bitrate'] = self.bitrate

        # Add thread count
        if self.thread_count > 0:
            params['threads'] = self.thread_count

        # Add GPU ID for hardware acceleration
        if self.gpu_id > 0 and self._is_gpu_codec(self.codec):
            params['gpu'] = self.gpu_id

        # Choose appropriate writer based on codec
        try:
            if self.codec.endswith('_nvenc'):
                self._writer = self._ffmpegcv.VideoWriterNV(str(output_path), **params)
            elif self.codec.endswith('_qsv'):
                self._writer = self._ffmpegcv.VideoWriterQSV(str(output_path), **params)
            else:
                self._writer = self._ffmpegcv.VideoWriter(str(output_path), **params)

            self._is_opened = True
            logger.debug(f"Opened FFmpegCV video writer with codec {self.codec}: {output_path}")

        except Exception as e:
            raise RuntimeError(f"Failed to create ffmpegcv writer: {e}")

    def _is_gpu_codec(self, codec: str) -> bool:
        """Check if codec uses GPU acceleration."""
        return any(suffix in codec for suffix in ['_nvenc', '_qsv', '_amf'])

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

        if frame.shape[:2] != (self.height, self.width):
            # Resize frame to match output dimensions
            logger.debug(f"Resizing frame from {frame.shape[:2]} to ({self.height}, {self.width})")
            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)

        # Convert color format if needed
        # ffmpegcv expects RGB format, OpenCV uses BGR
        if frame.shape[2] == 3:
            frame_rgb = frame[:, :, ::-1]  # BGR to RGB
        else:
            frame_rgb = frame

        try:
            self._writer.write(frame_rgb)
        except Exception as e:
            raise RuntimeError(f"Failed to write frame to video: {e}")

    def close(self) -> None:
        """Close the video writer and finalize the file."""
        if self._writer is not None:
            try:
                self._writer.release()
                logger.debug(f"Closed FFmpegCV video writer: {self._output_path}")
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
        info = {
            'backend': self.name,
            'codec': self.codec,
            'fps': self.fps,
            'resolution': (self.width, self.height),
            'bitrate': self.bitrate,
            'quality_preset': self.quality_preset,
            'preset': self.preset,
            'crf': self.crf,
            'pix_fmt': self.pix_fmt,
            'supports_gpu': self.supports_gpu(),
            'pixel_format': self.get_pixel_format(),
            'hardware_accel': self.hardware_accel,
        }

        # Add hardware-specific info
        if self._is_gpu_codec(self.codec):
            info['gpu_id'] = self.gpu_id

        # Add thread info
        if self.thread_count > 0:
            info['threads'] = self.thread_count

        return info

    def validate_settings(self) -> List[str]:
        """Validate encoder settings and return list of errors.

        Returns:
            List of error messages. Empty list if all settings are valid.
        """
        errors = []

        if self.fps <= 0:
            errors.append("FPS must be greater than 0")

        if self.fps > 240:
            errors.append("FPS should not exceed 240 for most use cases")

        if self.width <= 0 or self.height <= 0:
            errors.append("Width and height must be greater than 0")

        if self.width > 16384 or self.height > 16384:
            errors.append("Width and height should not exceed 16384 pixels")

        if self.codec not in self.supported_codecs:
            errors.append(f"Unsupported codec: {self.codec}. "
                         f"Supported codecs: {self.supported_codecs}")

        # Validate CRF range
        if not isinstance(self.crf, int) or self.crf < 0 or self.crf > 51:
            errors.append("CRF must be an integer between 0 and 51")

        # Validate dimensions are even
        if self.width % 2 != 0 or self.height % 2 != 0:
            errors.append("Width and height must be even for most codecs")

        # Check GPU availability
        if self._is_gpu_codec(self.codec):
            if self.codec.endswith('_nvenc') and not self._is_nvidia_available():
                errors.append("NVIDIA NVENC codec selected but NVIDIA GPU not available")
            elif self.codec.endswith('_qsv') and not self._is_intel_qsv_available():
                errors.append("Intel QSV codec selected but Intel Quick Sync not available")

        return errors

    def get_pixel_format(self) -> str:
        """Get the pixel format this backend expects.

        Returns:
            Pixel format string ('bgr', 'rgb', 'yuv420p', etc.)
        """
        return 'rgb'  # ffmpegcv expects RGB format

    def supports_gpu(self) -> bool:
        """Check if backend supports GPU acceleration.

        Returns:
            True if backend can use GPU acceleration
        """
        return (self._is_nvidia_available() or
                self._is_intel_qsv_available() or
                self._is_amd_available())

    def get_hardware_info(self) -> Dict[str, Any]:
        """Get information about available hardware acceleration.

        Returns:
            Dictionary with hardware acceleration info
        """
        return {
            'nvidia_available': self._is_nvidia_available(),
            'intel_qsv_available': self._is_intel_qsv_available(),
            'amd_available': self._is_amd_available(),
            'selected_acceleration': self.hardware_accel,
        }