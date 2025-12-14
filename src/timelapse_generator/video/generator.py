"""Video generation from image sequences."""

import os
import time
from pathlib import Path
from typing import List, Optional, Tuple, Iterator, Dict, Any

import cv2
import numpy as np
from tqdm import tqdm

from ..config.settings import settings
from ..utils.file_utils import (
    find_image_files,
    validate_image_sequence,
    ensure_output_directory,
    estimate_output_size,
    get_common_image_properties
)
from ..utils.logging import get_logger
from .backends import create_backend, BackendRegistry
from .encoder import VideoEncoder

logger = get_logger(__name__)


class VideoGenerator:
    """Generate timelapse videos from image sequences."""

    def __init__(
        self,
        fps: int = 30,
        quality: str = 'medium',
        backend: Optional[str] = None,
        codec: Optional[str] = None,
        bitrate: Optional[str] = None,
        resolution: Optional[Tuple[int, int]] = None,
        show_progress: bool = True,
        backend_fallback: bool = True
    ):
        """Initialize video generator.

        Args:
            fps: Frames per second
            quality: Quality preset (low, medium, high, ultra)
            backend: Video encoding backend (opencv, ffmpegcv, auto)
            codec: Video codec
            bitrate: Custom bitrate
            resolution: Output resolution (width, height)
            show_progress: Whether to show progress meter
            backend_fallback: Enable fallback to other backends if primary fails
        """
        self.fps = fps
        self.quality = quality
        self.resolution = resolution
        self.show_progress = show_progress
        self.backend_fallback = backend_fallback

        # Determine backend
        if backend is None:
            backend = self._select_best_backend()

        self.backend_name = backend
        self.codec = codec
        self.bitrate = bitrate

        # Keep encoder for compatibility and helper methods
        self.encoder = VideoEncoder(
            quality=quality,
            codec=codec,
            custom_bitrate=bitrate
        )

        logger.info(f"Video generator initialized: fps={fps}, quality={quality}, backend={backend}, codec={codec}, bitrate={bitrate}, resolution={resolution}, show_progress={show_progress}")

    def _select_best_backend(self) -> str:
        """Select the best available backend."""
        # Check configuration first
        config = settings.video

        if config.auto_select_backend:
            # Auto-select based on availability and priority
            available = BackendRegistry.get_available_backends()
            if not available:
                raise RuntimeError("No video backends are available")

            # Filter by enabled backends
            enabled_backends = []
            for name in available.keys():
                if name in config.backends and config.backends[name].enabled:
                    enabled_backends.append(name)

            if not enabled_backends:
                # Fall back to any available backend
                enabled_backends = list(available.keys())

            # Sort by priority (lower = higher priority)
            enabled_backends.sort(key=lambda x: config.backends[x].priority if x in config.backends else 100)

            return enabled_backends[0]

        # Use configured backend
        return config.backend

    def generate_video(
        self,
        input_dir: Path,
        output_path: Path,
        progress_callback: Optional[callable] = None,
        create_thumbnail: bool = False
    ) -> Dict[str, Any]:
        """Generate video from images in input directory.

        Args:
            input_dir: Directory containing input images
            output_path: Output video file path
            progress_callback: Callback function for progress updates
            create_thumbnail: Whether to create a thumbnail image

        Returns:
            Dictionary with generation results
        """
        logger.info(f"Starting video generation from {input_dir} to {output_path}")

        # Ensure output directory exists
        ensure_output_directory(output_path)

        # Find and validate images
        try:
            image_files = find_image_files(input_dir)
            logger.info(f"Found {len(image_files)} images")
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to find images: {e}")
            raise

        # Validate image sequence
        valid_images, errors = validate_image_sequence(image_files)
        if errors:
            logger.warning(f"Found {len(errors)} invalid images that will be skipped")
            for error in errors:
                logger.debug(f"Invalid image: {error}")

        if not valid_images:
            logger.error("No valid images found for video generation")
            raise ValueError("No valid images found")

        logger.info(f"Using {len(valid_images)} valid images for video generation")

        # Get image properties and prepare dimensions
        props = get_common_image_properties(valid_images)
        if props["sizes_consistent"]:
            logger.info(f"Images have consistent dimensions: {props['common_size']}")
            width, height = props["common_size"]
        else:
            logger.warning("Images have inconsistent dimensions, using first image dimensions")
            first_info = cv2.imread(str(valid_images[0]))
            height, width = first_info.shape[:2]

        # Apply resolution scaling if specified
        if self.resolution:
            width, height = self.encoder.get_resolution_for_aspect_ratio(
                width, height, self.resolution
            )

        # Ensure even dimensions for codec compatibility
        width, height = self.encoder.ensure_even_dimensions(width, height)

        logger.info(f"Output video dimensions: {width}x{height}")

        # Create and initialize backend
        backend = self._create_backend_instance(width, height)

        try:
            # Generate video using the backend
            return self._generate_with_backend(
                backend, valid_images, output_path, width, height,
                progress_callback, create_thumbnail, props
            )
        finally:
            # Ensure backend is closed
            try:
                backend.close()
            except:
                pass

    def _create_backend_instance(self, width: int, height: int):
        """Create a backend instance with fallback support."""
        backend_kwargs = {
            'fps': self.fps,
            'width': width,
            'height': height,
            'codec': self.codec,
            'bitrate': self.bitrate,
            'quality_preset': self.quality
        }

        # Add backend-specific settings from configuration
        config = settings.video
        backend_config = config.backends.get(self.backend_name)
        if backend_config:
            backend_kwargs.update(backend_config.settings)

        # Try primary backend
        try:
            logger.info(f"Creating backend: {self.backend_name}")
            return create_backend(self.backend_name, **backend_kwargs)
        except Exception as e:
            logger.error(f"Failed to create backend {self.backend_name}: {e}")
            if not self.backend_fallback:
                raise RuntimeError(f"Failed to create backend {self.backend_name}: {e}")

        # Try fallback backends
        available = BackendRegistry.get_available_backends()
        for backend_name in available.keys():
            if backend_name == self.backend_name:
                continue

            try:
                logger.info(f"Trying fallback backend: {backend_name}")
                return create_backend(backend_name, **backend_kwargs)
            except Exception as e:
                logger.warning(f"Fallback backend {backend_name} failed: {e}")
                continue

        raise RuntimeError(f"Failed to create any video backend. Tried: {list(available.keys())}")

    def _generate_with_backend(self, backend, valid_images, output_path, width, height,
                              progress_callback, create_thumbnail, props):
        """Generate video using a specific backend."""
        logger.info(f"Using backend: {backend.name}")
        backend_info = backend.get_encoder_info()
        logger.info(f"Backend settings: {backend_info}")

        # Open video writer
        backend.open(output_path)

        try:
            # Process each image with enhanced progress tracking
            frame_count = 0
            skipped_count = 0
            start_time = time.time()
            total_images = len(valid_images)

            # Progress tracking setup
            progress_context = tqdm(
                total=total_images,
                desc=f"Creating timelapse ({backend.name})",
                unit="images",
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                dynamic_ncols=True,
                disable=not self.show_progress
            ) if self.show_progress else None

            def update_progress_info(frames_processed, total_frames, skips, fps_rate=None, video_duration=None, eta_seconds=None):
                """Update progress display."""
                if not progress_context:
                    return

                postfix = {
                    "frames": f"{frames_processed}/{total_frames}",
                    "fps": f"{fps_rate:.1f}" if fps_rate else "0.0",
                    "video": f"{video_duration:.1f}s" if video_duration else "0.0s"
                }

                # Add success rate
                success_rate = (frames_processed / (total_frames if total_frames > 0 else 1)) * 100
                postfix["success"] = f"{success_rate:.0f}%"

                # Add ETA if available
                if eta_seconds is not None:
                    postfix["eta"] = f"{eta_seconds:.0f}s"

                # Show skipped count only if there are skips
                if skips > 0:
                    postfix["skipped"] = skips

                progress_context.set_postfix(postfix)

            # Initialize progress display
            if progress_context:
                progress_context.set_postfix({
                    "frames": "0/0",
                    "success": "0%",
                    "fps": "0.0",
                    "video": "0.0s"
                })

            # Process images
            for i, image_path in enumerate(valid_images):
                try:
                    # Read and process image
                    frame = self._process_image(image_path, width, height, backend.get_pixel_format())

                    if frame is not None:
                        backend.write_frame(frame)
                        frame_count += 1

                        # Calculate timing and statistics
                        elapsed_time = time.time() - start_time
                        if elapsed_time > 0:
                            images_per_sec = (i + 1) / elapsed_time
                            remaining_images = total_images - (i + 1)
                            eta_seconds = remaining_images / max(images_per_sec, 0.001)
                            video_duration = frame_count / self.fps

                            # Update progress display
                            update_progress_info(
                                frame_count, total_images, skipped_count,
                                images_per_sec, video_duration, eta_seconds
                            )

                            # Call progress callback with detailed info
                            if progress_callback:
                                progress = (i + 1) / total_images
                                progress_callback(progress, frame_count, total_images, images_per_sec, eta_seconds)
                        else:
                            # Initial update before we have timing data
                            update_progress_info(frame_count, total_images, skipped_count)

                    else:
                        skipped_count += 1
                        logger.warning(f"Skipped invalid frame: {image_path}")

                        # Update progress for skipped frame periodically
                        if i > 0 and (i + 1) % 10 == 0:  # Update every 10 frames
                            elapsed_time = time.time() - start_time
                            if elapsed_time > 0:
                                images_per_sec = (i + 1) / elapsed_time
                                update_progress_info(
                                    frame_count, total_images, skipped_count,
                                    images_per_sec, None, None
                                )

                    # Update progress bar
                    if progress_context:
                        progress_context.update(1)

                except Exception as e:
                    logger.error(f"Error processing image {image_path}: {e}")
                    skipped_count += 1
                    if progress_context:
                        progress_context.update(1)
                    continue

            # Clean up progress context
            if progress_context:
                progress_context.close()

            # Final progress update
            total_time = time.time() - start_time
            if total_time > 0:
                avg_fps = total_images / total_time
                final_success_rate = (frame_count / total_images) * 100
                logger.info(f"Processing completed: {final_success_rate:.1f}% success rate, {avg_fps:.1f} avg fps")

            # Close video writer
            backend.close()

            # Verify output file
            if not output_path.exists():
                logger.error("Video file was not created")
                raise RuntimeError("Video file was not created")

            output_size = output_path.stat().st_size

            logger.info(f"Video generation completed: {frame_count} frames, {output_size:,} bytes")

            # Create thumbnail if requested
            thumbnail_info = None
            if create_thumbnail:
                logger.info("Creating thumbnail from middle frame...")
                thumbnail_info = self._create_thumbnail(valid_images, output_path, width, height)

            return {
                "success": True,
                "output_path": str(output_path),
                "backend_used": backend.name,
                "encoder_info": backend_info,
                "frame_count": frame_count,
                "skipped_count": skipped_count,
                "output_size_bytes": output_size,
                "output_size_mb": output_size / (1024 * 1024),
                "duration_seconds": frame_count / self.fps,
                "resolution": (width, height),
                "fps": self.fps,
                "input_properties": props,
                "thumbnail": thumbnail_info
            }

        except Exception as e:
            logger.error(f"Error during video generation: {e}")
            # Cleanup
            try:
                backend.close()
            except:
                pass
            if output_path.exists():
                output_path.unlink()
            raise

    def _process_image(self, image_path: Path, target_width: int, target_height: int, pixel_format: str = 'bgr') -> Optional[np.ndarray]:
        """Process a single image for video.

        Args:
            image_path: Path to input image
            target_width: Target width
            target_height: Target height
            pixel_format: Expected pixel format ('bgr', 'rgb')

        Returns:
            Processed image as numpy array or None if failed
        """
        try:
            # Read image (OpenCV reads in BGR format)
            img = cv2.imread(str(image_path))
            if img is None:
                logger.warning(f"Failed to read image: {image_path}")
                return None

            # Resize if necessary
            current_height, current_width = img.shape[:2]
            if current_width != target_width or current_height != target_height:
                img = cv2.resize(img, (target_width, target_height), interpolation=cv2.INTER_AREA)

            # Convert to requested pixel format if needed
            if pixel_format == 'rgb' and len(img.shape) == 3 and img.shape[2] == 3:
                # Convert from BGR to RGB
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            elif pixel_format == 'bgr':
                # Already in BGR format (OpenCV default)
                pass
            else:
                logger.warning(f"Unsupported pixel format: {pixel_format}, using BGR")

            return img

        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            return None

    def _create_thumbnail(self, valid_images: List[Path], output_path: Path, width: int, height: int) -> Dict[str, Any]:
        """Create a thumbnail from the middle image in the sequence.

        Args:
            valid_images: List of valid image files
            output_path: Output video path (used for naming thumbnail)
            width: Target width (video resolution)
            height: Target height (video resolution)

        Returns:
            Dictionary with thumbnail information or None if failed
        """
        try:
            if not valid_images:
                logger.error("No images available for thumbnail creation")
                return None

            # Find the middle image
            middle_index = len(valid_images) // 2
            middle_image_path = valid_images[middle_index]

            logger.info(f"Using middle image for thumbnail: {middle_image_path.name}")

            # Read and process the image
            thumbnail_img = self._process_image(middle_image_path, width, height)
            if thumbnail_img is None:
                logger.error(f"Failed to process thumbnail image: {middle_image_path}")
                return None

            # Generate thumbnail filename
            video_name = output_path.stem
            video_dir = output_path.parent
            input_extension = middle_image_path.suffix.lower()

            thumbnail_filename = f"{video_name}_thumbnail{input_extension}"
            thumbnail_path = video_dir / thumbnail_filename

            # Save thumbnail with high quality
            # Convert BGR to RGB for saving with PIL for better quality
            try:
                from PIL import Image
                import numpy as np

                # Convert BGR to RGB
                rgb_img = cv2.cvtColor(thumbnail_img, cv2.COLOR_BGR2RGB)

                # Create PIL Image and save with high quality
                pil_img = Image.fromarray(rgb_img)

                # Use high quality settings
                save_kwargs = {}
                if input_extension in ['.jpg', '.jpeg']:
                    save_kwargs['quality'] = 95
                    save_kwargs['optimize'] = True
                elif input_extension == '.png':
                    save_kwargs['optimize'] = True

                pil_img.save(thumbnail_path, **save_kwargs)

            except ImportError:
                # Fallback to OpenCV if PIL is not available
                cv2.imwrite(str(thumbnail_path), thumbnail_img, [cv2.IMWRITE_JPEG_QUALITY, 95])

            # Verify thumbnail was created
            if not thumbnail_path.exists():
                logger.error(f"Thumbnail file was not created: {thumbnail_path}")
                return None

            thumbnail_size = thumbnail_path.stat().st_size

            logger.info(f"Thumbnail created successfully: {thumbnail_path}")

            return {
                "thumbnail_path": str(thumbnail_path),
                "thumbnail_size_bytes": thumbnail_size,
                "thumbnail_size_kb": thumbnail_size / 1024,
                "source_image": str(middle_image_path),
                "resolution": (width, height),
                "middle_index": middle_index,
                "total_images": len(valid_images)
            }

        except Exception as e:
            logger.error(f"Error creating thumbnail: {e}")
            return None

    def estimate_output_info(self, input_dir: Path) -> Dict[str, Any]:
        """Estimate output video information without generating.

        Args:
            input_dir: Directory containing input images

        Returns:
            Dictionary with estimated output information
        """
        try:
            image_files = find_image_files(input_dir)
            logger.info(f"Found {len(image_files)} images")
            valid_images, _ = validate_image_sequence(image_files)
            logger.info(f"Found {len(valid_images)} valid images")

            if not valid_images:
                return {"error": "No valid images found"}

            # Get image properties
            props = get_common_image_properties(valid_images)

            # Estimate using current settings
            estimate = estimate_output_size(valid_images, self.fps, self._get_quality_factor())

            # Calculate dimensions
            if props["sizes_consistent"]:
                width, height = props["common_size"]
            else:
                # Use first image as reference
                first_info = cv2.imread(str(valid_images[0]))
                height, width = first_info.shape[:2]

            if self.resolution:
                width, height = self.encoder.get_resolution_for_aspect_ratio(
                    width, height, self.resolution
                )

            width, height = self.encoder.ensure_even_dimensions(width, height)

            estimate.update({
                "input_count": len(valid_images),
                "resolution": (width, height),
                "fps": self.fps,
                "quality": self.quality,
                "input_size_mb": props.get("total_size_mb", 0),
                "compression_ratio": props.get("total_size_mb", 0) / max(estimate["estimated_size_mb"], 0.1)
            })

            return estimate

        except Exception as e:
            logger.error(f"Error estimating output info: {e}")
            return {"error": str(e)}

    def _get_quality_factor(self) -> float:
        """Get quality factor for size estimation."""
        quality_factors = {
            'low': 0.5,
            'medium': 1.0,
            'high': 1.5,
            'ultra': 2.0
        }
        return quality_factors.get(self.quality, 1.0)

    @staticmethod
    def get_video_info(video_path: Path) -> Dict[str, Any]:
        """Get information about a generated video file.

        Args:
            video_path: Path to video file

        Returns:
            Dictionary with video information
        """
        if not video_path.exists():
            return {"error": "Video file not found"}

        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return {"error": "Failed to open video file"}

            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            cap.release()

            # Calculate duration
            duration = frame_count / fps if fps > 0 else 0

            # Get file size
            file_size = video_path.stat().st_size

            return {
                "path": str(video_path),
                "fps": fps,
                "frame_count": frame_count,
                "width": width,
                "height": height,
                "resolution": (width, height),
                "duration_seconds": duration,
                "duration_formatted": f"{int(duration//60):02d}:{int(duration%60):02d}",
                "file_size_bytes": file_size,
                "file_size_mb": file_size / (1024 * 1024)
            }

        except Exception as e:
            return {"error": str(e)}