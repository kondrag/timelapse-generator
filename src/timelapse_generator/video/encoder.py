"""Video encoding configurations and utilities."""

from typing import Dict, Tuple, Optional

import cv2


class VideoEncoder:
    """Video encoder with configurable quality settings."""

    # Video codec mappings
    CODECS = {
        'mp4v': 'mp4v',
        'x264': 'XVID',  # Fallback for OpenCV
        'x265': 'X264',  # Fallback for OpenCV
        'avc1': 'mp4v',
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

    def __init__(self, quality: str = 'medium', codec: Optional[str] = None, custom_bitrate: Optional[str] = None):
        """Initialize video encoder.

        Args:
            quality: Quality preset (low, medium, high, ultra)
            codec: Video codec to use
            custom_bitrate: Custom bitrate override
        """
        self.quality = quality.lower()
        if self.quality not in self.QUALITY_PRESETS:
            raise ValueError(f"Invalid quality preset: {quality}. Valid options: {list(self.QUALITY_PRESETS.keys())}")

        # Load quality settings
        settings = self.QUALITY_PRESETS[self.quality].copy()

        # Override with custom settings
        if codec:
            settings['codec'] = codec
        if custom_bitrate:
            settings['bitrate'] = custom_bitrate

        self.codec = settings['codec']
        self.bitrate = settings['bitrate']
        self.crf = settings['crf']
        self.preset = settings['preset']

    def get_fourcc(self) -> int:
        """Get OpenCV FourCC codec identifier."""
        codec_name = self.CODECS.get(self.codec, self.codec)
        fourcc = cv2.VideoWriter_fourcc(*codec_name)
        return fourcc

    def get_ffmpeg_settings(self) -> Dict[str, str]:
        """Get FFmpeg encoding settings."""
        return {
            'codec': self.codec,
            'bitrate': self.bitrate,
            'crf': str(self.crf),
            'preset': self.preset,
            'pix_fmt': 'yuv420p'  # Better compatibility
        }

    def calculate_output_size(self, frame_count: int, fps: int) -> int:
        """Calculate estimated output file size in bytes.

        Args:
            frame_count: Number of frames
            fps: Frames per second

        Returns:
            Estimated file size in bytes
        """
        duration_seconds = frame_count / fps

        # Parse bitrate (e.g., '5M' -> 5,000,000)
        bitrate_value = self._parse_bitrate(self.bitrate)
        estimated_bits = bitrate_value * duration_seconds
        return estimated_bits // 8  # Convert to bytes

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

    def get_resolution_for_aspect_ratio(self, original_width: int, original_height: int, target_resolution: Optional[Tuple[int, int]] = None) -> Tuple[int, int]:
        """Calculate output resolution maintaining aspect ratio.

        Args:
            original_width: Original image width
            original_height: Original image height
            target_resolution: Target resolution (width, height) or None for original

        Returns:
            Output resolution (width, height)
        """
        if target_resolution is None:
            return original_width, original_height

        target_width, target_height = target_resolution
        original_aspect = original_width / original_height
        target_aspect = target_width / target_height

        # Maintain aspect ratio
        if abs(original_aspect - target_aspect) < 0.01:
            # Aspects are very similar, use target resolution
            return target_width, target_height
        elif original_aspect > target_aspect:
            # Original is wider, use target width and calculate height
            new_height = int(target_width / original_aspect)
            return target_width, new_height
        else:
            # Original is taller, use target height and calculate width
            new_width = int(target_height * original_aspect)
            return new_width, target_height

    @staticmethod
    def ensure_even_dimensions(width: int, height: int) -> Tuple[int, int]:
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