"""File utility functions for timelapse generation."""

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image


def natural_sort_key(s: str) -> List[int]:
    """Natural sorting key for strings with numbers.

    Example: 'img_001.jpg', 'img_010.jpg' will be sorted correctly.
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def find_image_files(directory: Path, pattern: str = "*.jpg") -> List[Path]:
    """Find and sort image files in a directory using natural sorting.

    Args:
        directory: Directory to search for images
        pattern: File pattern to match (default: "*.jpg")

    Returns:
        List of image file paths sorted naturally

    Raises:
        FileNotFoundError: If directory doesn't exist
        ValueError: If no images found
    """
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    image_files = []
    for ext in ["*.jpg", "*.jpeg", "*.JPG", "*.JPEG", "*.png", "*.PNG"]:
        image_files.extend(directory.glob(ext))

    if not image_files:
        raise ValueError(f"No images found in {directory}")
    else:
        logger.info(f"Found {len(image_files)} images in {directory}")

    # Sort naturally based on filename
    image_files.sort(key=lambda p: natural_sort_key(p.name))
    return image_files


def validate_image(image_path: Path) -> Tuple[bool, Optional[str]]:
    """Validate that an image file is readable and not corrupted.

    Args:
        image_path: Path to image file

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        with Image.open(image_path) as img:
            # Try to load the image data
            img.verify()

        # Reopen for size info after verify()
        with Image.open(image_path) as img:
            if img.size[0] < 1 or img.size[1] < 1:
                return False, f"Invalid image dimensions: {img.size}"

        return True, None
    except Exception as e:
        return False, f"Image validation failed: {e}"


def get_image_info(image_path: Path) -> dict:
    """Get information about an image file.

    Args:
        image_path: Path to image file

    Returns:
        Dictionary with image information
    """
    try:
        with Image.open(image_path) as img:
            return {
                "path": str(image_path),
                "size": img.size,  # (width, height)
                "mode": img.mode,
                "format": img.format,
                "file_size": image_path.stat().st_size
            }
    except Exception as e:
        return {
            "path": str(image_path),
            "error": str(e)
        }


def validate_image_sequence(image_files: List[Path]) -> Tuple[List[Path], List[dict]]:
    """Validate a sequence of image files.

    Args:
        image_files: List of image file paths

    Returns:
        Tuple of (valid_files, error_list)
    """
    valid_files = []
    errors = []

    for image_path in image_files:
        is_valid, error_msg = validate_image(image_path)
        if is_valid:
            valid_files.append(image_path)
        else:
            errors.append({
                "file": str(image_path),
                "error": error_msg
            })

    for error in errors:
        logger.error(f"Invalid image: {error['file']} - {error['error']}")
    return valid_files, errors


def ensure_output_directory(output_path: Path) -> Path:
    """Ensure output directory exists.

    Args:
        output_path: Output path (can be file or directory)

    Returns:
        Path to output directory
    """
    if output_path.suffix:
        # It's a file path, get parent directory
        output_dir = output_path.parent
    else:
        # It's a directory path
        output_dir = output_path

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_common_image_properties(image_files: List[Path]) -> dict:
    """Get common properties from a sequence of images.

    Args:
        image_files: List of image file paths

    Returns:
        Dictionary with common properties
    """
    if not image_files:
        return {}

    properties = get_image_info(image_files[0])
    if "error" in properties:
        return {}

    # Sample a few images to check for consistency
    sample_size = min(10, len(image_files))
    sample_files = image_files[::len(image_files)//sample_size + 1][:sample_size]

    common_size = properties["size"]
    common_mode = properties["mode"]
    sizes_consistent = True
    modes_consistent = True

    for img_path in sample_files[1:]:
        info = get_image_info(img_path)
        if "error" in info:
            continue

        if info["size"] != common_size:
            sizes_consistent = False
        if info["mode"] != common_mode:
            modes_consistent = False

    return {
        "count": len(image_files),
        "first_image": str(image_files[0]),
        "last_image": str(image_files[-1]),
        "common_size": common_size,
        "sizes_consistent": sizes_consistent,
        "common_mode": common_mode,
        "modes_consistent": modes_consistent,
        "total_size_mb": sum(img_path.stat().st_size for img_path in image_files) / (1024 * 1024)
    }


def estimate_output_size(
    image_files: List[Path],
    fps: int = 30,
    quality_factor: float = 1.0
) -> dict:
    """Estimate output video size and duration.

    Args:
        image_files: List of image file paths
        fps: Frames per second
        quality_factor: Quality factor for size estimation (1.0 = medium quality)

    Returns:
        Dictionary with size estimates
    """
    if not image_files:
        return {"duration_seconds": 0, "estimated_size_mb": 0}

    frame_count = len(image_files)
    duration_seconds = frame_count / fps

    # Estimate based on frame count, resolution, and quality
    if image_files:
        sample_info = get_image_info(image_files[len(image_files)//2])
        if "error" not in sample_info:
            width, height = sample_info["size"]
            pixels = width * height

            # Base bitrate estimate (bits per second)
            # This is a rough approximation
            base_bitrate = pixels * 0.1 * quality_factor  # Adjust for resolution
            base_bitrate = max(base_bitrate, 1_000_000)  # Minimum 1 Mbps
            base_bitrate = min(base_bitrate, 50_000_000)  # Maximum 50 Mbps

            estimated_bits = base_bitrate * duration_seconds
            estimated_size_mb = estimated_bits / (8 * 1024 * 1024)
        else:
            estimated_size_mb = frame_count * 0.1 * quality_factor  # Very rough fallback
    else:
        estimated_size_mb = 0

    return {
        "duration_seconds": duration_seconds,
        "duration_formatted": f"{int(duration_seconds//60):02d}:{int(duration_seconds%60):02d}",
        "frame_count": frame_count,
        "estimated_size_mb": estimated_size_mb,
        "fps": fps
    }