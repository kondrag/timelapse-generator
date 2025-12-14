"""
Video encoding backends for timelapse generation.

This module provides a pluggable architecture for video encoding backends,
allowing users to choose between different encoding technologies such as
OpenCV and FFmpegCV.
"""

from .base import VideoBackend
from .registry import BackendRegistry, create_backend, create_best_backend, list_available_backends

# Import and register backends
try:
    from .opencv_backend import OpenCVBackend
    BackendRegistry.register('opencv', OpenCVBackend)
except ImportError:
    # OpenCV is not available
    pass

try:
    from .ffmpegcv_backend import FFmpegCVBackend
    BackendRegistry.register('ffmpegcv', FFmpegCVBackend)
except ImportError:
    # FFmpegCV is not available
    pass

__all__ = [
    'VideoBackend',
    'BackendRegistry',
    'create_backend',
    'create_best_backend',
    'list_available_backends',
]

# Add backend classes to __all__ if they were successfully imported
try:
    __all__.append('OpenCVBackend')
except NameError:
    pass

try:
    __all__.append('FFmpegCVBackend')
except NameError:
    pass