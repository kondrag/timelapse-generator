"""Tests for video encoding backends."""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from timelapse_generator.video.backends import (
    BackendRegistry, create_backend, create_best_backend, list_available_backends
)
from timelapse_generator.video.backends.base import VideoBackend
from timelapse_generator.video.backends.opencv_backend import OpenCVBackend
from timelapse_generator.video.backends.ffmpegcv_backend import FFmpegCVBackend


class MockBackend(VideoBackend):
    """Mock backend for testing."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @property
    def name(self) -> str:
        return "mock"

    @property
    def supported_codecs(self) -> list:
        return ["mock_codec"]

    @property
    def supported_extensions(self) -> list:
        return [".mock"]

    def get_default_codec(self) -> str:
        return "mock_codec"

    def open(self, output_path: Path) -> None:
        pass

    def write_frame(self, frame: np.ndarray) -> None:
        pass

    def close(self) -> None:
        pass

    def get_encoder_info(self) -> dict:
        return {"backend": "mock"}

    def validate_settings(self) -> list:
        return []

    @staticmethod
    def is_available() -> bool:
        return True


class UnavailableBackend(VideoBackend):
    """Mock backend that's not available."""

    @property
    def name(self) -> str:
        return "unavailable"

    @property
    def supported_codecs(self) -> list:
        return []

    @property
    def supported_extensions(self) -> list:
        return []

    def get_default_codec(self) -> str:
        return ""

    @staticmethod
    def is_available() -> bool:
        return False

    def open(self, output_path: Path) -> None:
        pass

    def write_frame(self, frame: np.ndarray) -> None:
        pass

    def close(self) -> None:
        pass

    def get_encoder_info(self) -> dict:
        return {}

    def validate_settings(self) -> list:
        return []


class TestBackendRegistry:
    """Test backend registry functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Clear registry before each test
        BackendRegistry._backends.clear()
        BackendRegistry._availability_cache.clear()

    def test_register_backend(self):
        """Test backend registration."""
        # Register a backend
        BackendRegistry.register('test', MockBackend)
        assert BackendRegistry.get_backend('test') == MockBackend

    def test_register_overwrite(self):
        """Test overwriting existing backend."""
        BackendRegistry.register('test', MockBackend)
        BackendRegistry.register('test', MockBackend)  # Should overwrite without error

    def test_get_backend_nonexistent(self):
        """Test getting non-existent backend."""
        assert BackendRegistry.get_backend('nonexistent') is None

    def test_list_backends(self):
        """Test listing registered backends."""
        BackendRegistry.register('mock', MockBackend)
        BackendRegistry.register('unavailable', UnavailableBackend)

        backends = BackendRegistry.list_backends()
        assert 'mock' in backends
        assert 'unavailable' in backends

    def test_is_backend_available(self):
        """Test backend availability checking."""
        BackendRegistry.register('mock', MockBackend)
        BackendRegistry.register('unavailable', UnavailableBackend)

        assert BackendRegistry.is_backend_available('mock') is True
        assert BackendRegistry.is_backend_available('unavailable') is False
        assert BackendRegistry.is_backend_available('nonexistent') is False

    def test_get_available_backends(self):
        """Test getting only available backends."""
        BackendRegistry.register('mock', MockBackend)
        BackendRegistry.register('unavailable', UnavailableBackend)

        available = BackendRegistry.get_available_backends()
        assert 'mock' in available
        assert 'unavailable' not in available

    def test_get_backend_priority(self):
        """Test backend priority retrieval."""
        BackendRegistry.register('mock', MockBackend)

        # Should have default priority
        assert BackendRegistry.get_backend_priority('mock') == 100

    def test_get_best_backend(self):
        """Test getting best available backend."""
        BackendRegistry.register('mock', MockBackend)
        BackendRegistry.register('unavailable', UnavailableBackend)

        assert BackendRegistry.get_best_backend() == 'mock'

    def test_get_best_backend_none_available(self):
        """Test getting best backend when none are available."""
        BackendRegistry.register('unavailable', UnavailableBackend)

        assert BackendRegistry.get_best_backend() is None

    def test_unregister_backend(self):
        """Test backend unregistration."""
        BackendRegistry.register('mock', MockBackend)
        assert BackendRegistry.get_backend('mock') is not None

        BackendRegistry.unregister('mock')
        assert BackendRegistry.get_backend('mock') is None

    def test_get_backend_info(self):
        """Test getting backend information."""
        BackendRegistry.register('mock', MockBackend)

        info = BackendRegistry.get_backend_info()
        assert 'mock' in info
        assert info['mock']['name'] == 'mock'
        assert info['mock']['available'] is True

    def test_clear_cache(self):
        """Test clearing availability cache."""
        BackendRegistry.register('mock', MockBackend)

        # Check availability to populate cache
        BackendRegistry.is_backend_available('mock')
        assert len(BackendRegistry._availability_cache) > 0

        # Clear cache
        BackendRegistry.clear_cache()
        assert len(BackendRegistry._availability_cache) == 0


class TestBackendFactory:
    """Test backend factory functions."""

    def setup_method(self):
        """Set up test environment."""
        BackendRegistry._backends.clear()
        BackendRegistry.register('mock', MockBackend)

    def test_create_backend(self):
        """Test creating a backend instance."""
        backend = create_backend('mock', fps=30, width=1920, height=1080)
        assert isinstance(backend, MockBackend)
        assert backend.kwargs['fps'] == 30
        assert backend.kwargs['width'] == 1920
        assert backend.kwargs['height'] == 1080

    def test_create_backend_unknown(self):
        """Test creating unknown backend raises error."""
        with pytest.raises(ValueError, match="Unknown backend"):
            create_backend('unknown')

    def test_create_backend_unavailable(self):
        """Test creating unavailable backend raises error."""
        BackendRegistry.register('unavailable', UnavailableBackend)

        with pytest.raises(ValueError, match="not available"):
            create_backend('unavailable')

    def test_create_best_backend(self):
        """Test creating best available backend."""
        backend = create_best_backend(fps=30, width=1920, height=1080)
        assert isinstance(backend, MockBackend)

    def test_create_best_backend_none_available(self):
        """Test creating best backend when none available raises error."""
        BackendRegistry._backends.clear()

        with pytest.raises(RuntimeError, match="No video backends are available"):
            create_best_backend()

    def test_list_available_backends(self):
        """Test listing available backends."""
        BackendRegistry.register('mock', MockBackend)
        BackendRegistry.register('unavailable', UnavailableBackend)

        available = list_available_backends()
        assert 'mock' in available
        assert 'unavailable' not in available


@pytest.mark.skipif(not OpenCVBackend.is_available(), reason="OpenCV not available")
class TestOpenCVBackend:
    """Test OpenCV backend."""

    def test_backend_properties(self):
        """Test backend properties."""
        backend = OpenCVBackend(fps=30, width=640, height=480)

        assert backend.name == "opencv"
        assert "mp4v" in backend.supported_codecs
        assert ".mp4" in backend.supported_extensions
        assert backend.get_default_codec() == "mp4v"

    def test_validate_settings(self):
        """Test settings validation."""
        backend = OpenCVBackend(fps=30, width=640, height=480)
        errors = backend.validate_settings()
        assert len(errors) == 0

    def test_validate_invalid_settings(self):
        """Test invalid settings validation."""
        backend = OpenCVBackend(fps=0, width=640, height=480)
        errors = backend.validate_settings()
        assert any("FPS must be greater than 0" in e for e in errors)

    def test_get_pixel_format(self):
        """Test pixel format."""
        backend = OpenCVBackend(fps=30, width=640, height=480)
        assert backend.get_pixel_format() == 'bgr'

    def test_supports_gpu(self):
        """Test GPU support."""
        backend = OpenCVBackend(fps=30, width=640, height=480)
        assert backend.supports_gpu() is False

    def test_ensure_even_dimensions(self):
        """Test even dimension enforcement."""
        backend = OpenCVBackend(fps=30, width=641, height=481)
        # Should be made even during initialization
        assert backend.width % 2 == 0
        assert backend.height % 2 == 0

    @pytest.mark.skipif(not OpenCVBackend.is_available(), reason="OpenCV not available")
    def test_write_frames(self, tmp_path):
        """Test writing frames."""
        backend = OpenCVBackend(fps=30, width=320, height=240)
        output_path = tmp_path / "test.mp4"

        backend.open(output_path)

        # Write test frames
        for i in range(10):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            frame[:, :, 0] = i * 25  # Vary red channel
            backend.write_frame(frame)

        backend.close()

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_get_encoder_info(self):
        """Test encoder info."""
        backend = OpenCVBackend(fps=30, width=1920, height=1080, codec='mp4v')
        info = backend.get_encoder_info()

        assert info['backend'] == 'opencv'
        assert info['codec'] == 'mp4v'
        assert info['fps'] == 30
        assert info['resolution'] == (1920, 1080)
        assert 'supports_gpu' in info


@pytest.mark.skipif(not FFmpegCVBackend.is_available(), reason="FFmpegCV not available")
class TestFFmpegCVBackend:
    """Test FFmpegCV backend."""

    def test_backend_properties(self):
        """Test backend properties."""
        backend = FFmpegCVBackend(fps=30, width=640, height=480)

        assert backend.name == "ffmpegcv"
        assert "libx264" in backend.supported_codecs
        assert ".mp4" in backend.supported_extensions
        assert backend.get_default_codec() == "libx264"

    def test_get_pixel_format(self):
        """Test pixel format."""
        backend = FFmpegCVBackend(fps=30, width=640, height=480)
        assert backend.get_pixel_format() == 'rgb'

    def test_quality_preset_mapping(self):
        """Test quality preset mapping."""
        backend = FFmpegCVBackend(fps=30, width=640, height=480)
        assert backend.FFMPEG_PRESETS['low'] == 'fast'
        assert backend.FFMPEG_PRESETS['ultra'] == 'veryslow'

    def test_crf_values(self):
        """Test CRF values for quality levels."""
        backend = FFmpegCVBackend(fps=30, width=640, height=480)
        assert backend.CRF_VALUES['ultra'] == 15
        assert backend.CRF_VALUES['low'] == 28

    def test_validate_settings(self):
        """Test settings validation."""
        backend = FFmpegCVBackend(fps=30, width=640, height=480)
        errors = backend.validate_settings()
        assert len(errors) == 0

    def test_validate_invalid_crf(self):
        """Test invalid CRF value."""
        backend = FFmpegCVBackend(fps=30, width=640, height=480, crf=52)  # Too high
        errors = backend.validate_settings()
        assert any("CRF must be an integer between 0 and 51" in e for e in errors)

    @pytest.mark.skipif(not FFmpegCVBackend.is_available(), reason="FFmpegCV not available")
    def test_write_frames(self, tmp_path):
        """Test writing frames."""
        backend = FFmpegCVBackend(fps=30, width=320, height=240)
        output_path = tmp_path / "test.mp4"

        backend.open(output_path)

        # Write test frames (BGR format, will be converted to RGB)
        for i in range(10):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            frame[:, :, 0] = i * 25  # Vary blue channel (red in RGB)
            backend.write_frame(frame)

        backend.close()

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_get_encoder_info(self):
        """Test encoder info."""
        backend = FFmpegCVBackend(fps=30, width=1920, height=1080, codec='libx264')
        info = backend.get_encoder_info()

        assert info['backend'] == 'ffmpegcv'
        assert info['codec'] == 'libx264'
        assert info['fps'] == 30
        assert info['resolution'] == (1920, 1080)
        assert 'crf' in info
        assert 'preset' in info

    def test_get_hardware_info(self):
        """Test hardware acceleration info."""
        backend = FFmpegCVBackend(fps=30, width=1920, height=1080)
        hw_info = backend.get_hardware_info()

        assert 'nvidia_available' in hw_info
        assert 'intel_qsv_available' in hw_info
        assert 'amd_available' in hw_info


class TestBackendIntegration:
    """Test backend integration with the system."""

    def test_opencv_registration(self):
        """Test OpenCV backend is automatically registered."""
        from timelapse_generator.video.backends import BackendRegistry

        if OpenCVBackend.is_available():
            assert BackendRegistry.is_backend_available('opencv')
        else:
            assert not BackendRegistry.is_backend_available('opencv')

    def test_ffmpegcv_registration(self):
        """Test FFmpegCV backend is automatically registered."""
        from timelapse_generator.video.backends import BackendRegistry

        if FFmpegCVBackend.is_available():
            assert BackendRegistry.is_backend_available('ffmpegcv')
        else:
            assert not BackendRegistry.is_backend_available('ffmpegcv')

    @patch('timelapse_generator.video.backends.opencv_backend.cv2')
    def test_opencv_backend_unavailable(self, mock_cv2):
        """Test OpenCV backend when cv2 is not available."""
        mock_cv2.VideoWriter.side_effect = ImportError("No module named 'cv2'")

        backend = OpenCVBackend(fps=30, width=640, height=480)
        assert backend.is_available() is False

    @patch('timelapse_generator.video.backends.ffmpegcv_backend.importlib')
    def test_ffmpegcv_backend_unavailable(self, mock_importlib):
        """Test FFmpegCV backend when ffmpegcv is not available."""
        mock_importlib.import_module.side_effect = ImportError("No module named 'ffmpegcv'")

        assert FFmpegCVBackend.is_available() is False


if __name__ == '__main__':
    pytest.main([__file__])