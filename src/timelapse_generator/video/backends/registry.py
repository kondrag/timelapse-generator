"""
Registry for managing video encoding backends.
"""

from typing import Dict, Type, List, Optional, Any
import logging
from .base import VideoBackend

logger = logging.getLogger(__name__)


class BackendRegistry:
    """Registry for video encoding backends.

    This class manages the registration and discovery of video encoding backends.
    It provides a factory pattern for creating backend instances and can
    automatically detect which backends are available.
    """

    _backends: Dict[str, Type[VideoBackend]] = {}
    _availability_cache: Dict[str, bool] = {}

    @classmethod
    def register(cls, name: str, backend_class: Type[VideoBackend]) -> None:
        """Register a video backend.

        Args:
            name: Unique name for the backend
            backend_class: Backend class that inherits from VideoBackend

        Raises:
            ValueError: If a backend with the same name is already registered
        """
        if name in cls._backends:
            logger.warning(f"Backend '{name}' is already registered. Overwriting.")

        cls._backends[name] = backend_class
        # Clear availability cache for this backend
        cls._availability_cache.pop(name, None)
        logger.debug(f"Registered video backend: {name}")

    @classmethod
    def unregister(cls, name: str) -> None:
        """Unregister a video backend.

        Args:
            name: Name of the backend to unregister
        """
        if name in cls._backends:
            del cls._backends[name]
            cls._availability_cache.pop(name, None)
            logger.debug(f"Unregistered video backend: {name}")

    @classmethod
    def get_backend(cls, name: str) -> Optional[Type[VideoBackend]]:
        """Get a registered backend by name.

        Args:
            name: Name of the backend

        Returns:
            Backend class if found, None otherwise
        """
        return cls._backends.get(name)

    @classmethod
    def list_backends(cls) -> List[str]:
        """List all registered backend names.

        Returns:
            List of backend names in registration order
        """
        return list(cls._backends.keys())

    @classmethod
    def get_available_backends(cls) -> Dict[str, Type[VideoBackend]]:
        """Get all registered backends that are available.

        Returns:
            Dictionary mapping backend names to their classes
            for backends that have their dependencies installed
        """
        available = {}
        for name, backend_class in cls._backends.items():
            if cls.is_backend_available(name):
                available[name] = backend_class
        return available

    @classmethod
    def is_backend_available(cls, name: str) -> bool:
        """Check if a specific backend is available.

        Args:
            name: Name of the backend to check

        Returns:
            True if backend is available, False otherwise
        """
        # Check cache first
        if name in cls._availability_cache:
            return cls._availability_cache[name]

        backend_class = cls._backends.get(name)
        if backend_class is None:
            cls._availability_cache[name] = False
            return False

        try:
            # Test if backend is available (dependencies installed)
            available = backend_class.is_available()
            cls._availability_cache[name] = available
            return available
        except Exception as e:
            logger.debug(f"Error checking availability of backend '{name}': {e}")
            cls._availability_cache[name] = False
            return False

    @classmethod
    def get_backend_priority(cls, name: str) -> int:
        """Get priority for a backend (lower number = higher priority).

        Args:
            name: Name of the backend

        Returns:
            Priority value (100 for unknown backends)
        """
        backend_class = cls._backends.get(name)
        if backend_class is None:
            return 100

        # Check if backend has priority attribute
        if hasattr(backend_class, 'priority'):
            return backend_class.priority

        # Default priorities
        priorities = {
            'ffmpegcv': 90,  # Prefer FFmpegCV if available
            'opencv': 100,   # OpenCV fallback
        }
        return priorities.get(name, 100)

    @classmethod
    def get_best_backend(cls) -> Optional[str]:
        """Get the best available backend based on priority.

        Returns:
            Name of the best available backend, None if none available
        """
        available = cls.get_available_backends()
        if not available:
            return None

        # Sort by priority (lower number = higher priority)
        sorted_backends = sorted(
            available.keys(),
            key=lambda name: cls.get_backend_priority(name)
        )

        return sorted_backends[0] if sorted_backends else None

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the availability cache."""
        cls._availability_cache.clear()

    @classmethod
    def get_backend_info(cls) -> Dict[str, Dict[str, Any]]:
        """Get information about all registered backends.

        Returns:
            Dictionary with backend information
        """
        info = {}
        for name, backend_class in cls._backends.items():
            backend_info = {
                'name': name,
                'available': cls.is_backend_available(name),
                'priority': cls.get_backend_priority(name),
            }

            # Try to get more info from the backend class
            try:
                # Create a temporary instance to get properties
                temp_instance = backend_class(30, 320, 240)
                backend_info.update({
                    'supported_codecs': temp_instance.supported_codecs,
                    'supported_extensions': temp_instance.supported_extensions,
                    'default_codec': temp_instance.get_default_codec(),
                    'supports_gpu': temp_instance.supports_gpu(),
                    'pixel_format': temp_instance.get_pixel_format(),
                })
            except Exception as e:
                logger.debug(f"Could not get detailed info for backend '{name}': {e}")

            info[name] = backend_info

        return info


def create_backend(backend_name: str, **kwargs) -> VideoBackend:
    """Factory function to create a backend instance.

    Args:
        backend_name: Name of the backend to create
        **kwargs: Backend-specific initialization parameters

    Returns:
        Backend instance

    Raises:
        ValueError: If backend is unknown or unavailable
    """
    backend_class = BackendRegistry.get_backend(backend_name)
    if backend_class is None:
        raise ValueError(f"Unknown backend: {backend_name}")

    if not BackendRegistry.is_backend_available(backend_name):
        raise ValueError(f"Backend '{backend_name}' is not available (missing dependencies)")

    try:
        return backend_class(**kwargs)
    except Exception as e:
        raise RuntimeError(f"Failed to create backend '{backend_name}': {e}")


def create_best_backend(**kwargs) -> VideoBackend:
    """Create the best available backend.

    Args:
        **kwargs: Backend-specific initialization parameters

    Returns:
        Backend instance

    Raises:
        RuntimeError: If no backends are available
    """
    backend_name = BackendRegistry.get_best_backend()
    if backend_name is None:
        raise RuntimeError("No video backends are available")

    logger.info(f"Using best available backend: {backend_name}")
    return create_backend(backend_name, **kwargs)


def list_available_backends() -> List[str]:
    """Get a list of all available backend names.

    Returns:
        List of backend names that are available
    """
    return list(BackendRegistry.get_available_backends().keys())