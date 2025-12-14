"""Command line interface for the timelapse generator."""

import sys
from pathlib import Path
from typing import Optional

import click
from tqdm import tqdm

from .config.settings import settings
from .utils.logging import setup_logging, get_logger
from .video.generator import VideoGenerator
from .weather.noaa_client import NOAAClient
from .weather.kp_parser import KpIndexParser
from .youtube.uploader import YouTubeUploader
from .youtube.metadata import MetadataManager

logger = get_logger(__name__)


@click.group()
@click.option('--config', '-c', type=click.Path(exists=True), help='Configuration file path')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--log-file', type=click.Path(), help='Log file path')
@click.pass_context
def cli(ctx, config, verbose, log_file):
    """Timelapse Generator - Create timelapse videos from night sky images."""
    # Ensure context object exists
    ctx.ensure_object(dict)

    # Setup logging
    log_level = 'DEBUG' if verbose else settings.logging.level
    setup_logging(level=log_level, log_file=Path(log_file) if log_file else None)

    # Load configuration if specified
    if config:
        ctx.obj['config_path'] = Path(config)
        settings.load_with_env(ctx.obj['config_path'])
        logger.info(f"Using configuration: {config}")

    logger.info("Timelapse Generator CLI started")


@cli.command()
@click.argument('input_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument('output_file', type=click.Path(path_type=Path))
@click.option('--fps', '-f', type=int, default=None, help='Frames per second')
@click.option('--quality', '-q', type=click.Choice(['low', 'medium', 'high', 'ultra']), default=None, help='Video quality')
@click.option('--backend', '-b', type=click.Choice(['opencv', 'ffmpegcv', 'auto']), default=None, help='Video encoding backend')
@click.option('--codec', type=str, help='Video codec')
@click.option('--bitrate', type=str, help='Custom bitrate (e.g., "5M")')
@click.option('--resolution', type=str, help='Output resolution (e.g., "1920x1080")')
@click.option('--thumbnail', is_flag=True, help='Create thumbnail image from middle frame')
@click.option('--progress/--no-progress', default=True, help='Show/hide progress meter')
@click.option('--estimate-only', is_flag=True, help='Only estimate output, do not generate')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def generate(ctx, input_dir, output_file, fps, quality, backend, codec, bitrate, resolution, thumbnail, progress, estimate_only, yes):
    """Generate timelapse video from images."""
    try:
        # Use settings defaults if not specified
        fps = fps or settings.video.fps
        quality = quality or settings.video.quality
        backend = backend or settings.video.backend
        codec = codec or settings.video.codec
        bitrate = bitrate or settings.video.bitrate

        # Parse resolution if provided
        target_resolution = None
        if resolution:
            try:
                width, height = map(int, resolution.split('x'))
                target_resolution = (width, height)
            except ValueError:
                logger.error(f"Invalid resolution format: {resolution}")
                sys.exit(1)

        logger.info(f"Input directory: {input_dir}")
        logger.info(f"Output file: {output_file}")
        logger.info(f"Settings: fps={fps}, quality={quality}, backend={backend}, codec={codec}")

        # Check backend availability
        from .video.backends import BackendRegistry
        if backend != 'auto':
            if not BackendRegistry.is_backend_available(backend):
                logger.error(f"Backend '{backend}' is not available")
                available = BackendRegistry.get_available_backends()
                if available:
                    logger.info(f"Available backends: {', '.join(available.keys())}")
                sys.exit(1)

        # Create video generator
        generator = VideoGenerator(
            fps=fps,
            quality=quality,
            backend=backend,
            codec=codec,
            bitrate=bitrate,
            resolution=target_resolution,
            show_progress=progress
        )

        # Get estimate first
        estimate = generator.estimate_output_info(input_dir)
        if "error" in estimate:
            logger.error(f"Failed to estimate output: {estimate['error']}")
            sys.exit(1)

        click.echo("\n=== Video Generation Estimate ===")
        click.echo(f"Input images: {estimate['input_count']}")
        click.echo(f"Output resolution: {estimate['resolution'][0]}x{estimate['resolution'][1]}")
        click.echo(f"Duration: {estimate['duration_formatted']}")
        click.echo(f"Estimated size: {estimate['estimated_size_mb']:.1f} MB")
        click.echo(f"FPS: {estimate['fps']}")
        click.echo(f"Quality: {estimate['quality']}")

        if estimate_only:
            return

        # Ask for confirmation
        if not yes and not click.confirm("\nProceed with video generation?"):
            click.echo("Video generation cancelled.")
            return

        # Optional progress callback for additional monitoring
        def progress_callback(progress, current, total, speed=None, eta=None):
            # This callback is called by the video generator for additional progress tracking
            # The main progress bar is handled by the generator itself
            pass

        # Generate video with built-in enhanced progress meter
        result = generator.generate_video(input_dir, output_file, progress_callback, create_thumbnail=thumbnail)

        click.echo(f"\n✅ Video generated successfully!")
        click.echo(f"Output: {result['output_path']}")
        click.echo(f"Frames processed: {result['frame_count']}")
        click.echo(f"Frames skipped: {result['skipped_count']}")
        click.echo(f"Output size: {result['output_size_mb']:.1f} MB")
        click.echo(f"Duration: {result['duration_seconds']:.1f} seconds")
        click.echo(f"Resolution: {result['resolution'][0]}x{result['resolution'][1]}")

        # Show thumbnail information if created
        if result.get('thumbnail'):
            thumbnail_info = result['thumbnail']
            click.echo(f"Thumbnail: {thumbnail_info['thumbnail_path']}")
            click.echo(f"Thumbnail size: {thumbnail_info['thumbnail_size_kb']:.1f} KB")
            click.echo(f"Source image: {Path(thumbnail_info['source_image']).name}")
            click.echo(f"Middle frame: {thumbnail_info['middle_index'] + 1}/{thumbnail_info['total_images']}")

    except Exception as e:
        logger.error(f"Video generation failed: {e}")
        sys.exit(1)


@cli.command()
@click.option('--threshold', '-t', type=int, default=None, help='Kp index threshold')
@click.option('--no-cache', is_flag=True, help='Skip cached data')
def check_kp(threshold, no_cache):
    """Check current Kp index from NOAA."""
    try:
        threshold = threshold or settings.weather.kp_threshold

        click.echo(f"Checking Kp index against threshold {threshold}...")

        # Initialize NOAA client
        client = NOAAClient()

        # Get Kp data
        kp_data = client.get_kp_index(use_cache=not no_cache)
        kp_status = kp_data.get("data", {})

        if kp_status.get("status") != "success":
            click.echo(f"❌ Failed to get Kp data: {kp_status.get('message', 'Unknown error')}")
            return

        latest_kp = kp_status.get("latest_kp")
        max_kp = kp_status.get("max_kp")
        avg_kp = kp_status.get("average_kp")

        click.echo(f"\n=== Kp Index Data ===")
        click.echo(f"Latest Kp: {latest_kp}")
        click.echo(f"Maximum Kp: {max_kp}")
        click.echo(f"Average Kp: {avg_kp:.1f}")
        click.echo(f"Threshold: {threshold}")

        # Check threshold
        threshold_met = max_kp >= threshold
        if threshold_met:
            click.echo(f"\n✅ Kp threshold met! (Max Kp = {max_kp} >= {threshold})")
        else:
            click.echo(f"\n❌ Kp threshold not met (Max Kp = {max_kp} < {threshold})")

        # Check overnight Kp
        parser = KpIndexParser()
        overnight_result = parser.check_overnight_threshold(threshold)

        click.echo(f"\n=== Overnight Kp ===")
        click.echo(f"Night period: {overnight_result.get('night_start', 'Unknown')} to {overnight_result.get('night_end', 'Unknown')}")
        click.echo(f"Max Kp: {overnight_result.get('max_kp', 'Unknown')}")
        click.echo(f"Average Kp: {overnight_result.get('average_kp', 'Unknown')}")

        if overnight_result.get('threshold_met'):
            click.echo(f"✅ Overnight threshold met!")
        else:
            click.echo(f"❌ Overnight threshold not met")

    except Exception as e:
        logger.error(f"Kp check failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument('video_file', type=click.Path(exists=True, path_type=Path))
@click.option('--title', type=str, help='Custom video title')
@click.option('--description', type=str, help='Custom video description')
@click.option('--tags', type=str, help='Comma-separated tags')
@click.option('--privacy', type=click.Choice(['public', 'unlisted', 'private']), help='Privacy status')
@click.option('--dry-run', is_flag=True, help='Show metadata without uploading')
@click.option('--kp-index', type=float, help='Kp index for metadata')
@click.option('--location', type=str, help='Location for metadata')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompts')
def upload(video_file, title, description, tags, privacy, dry_run, kp_index, location, yes):
    """Upload video to YouTube."""
    try:
        if not settings.youtube.upload_enabled:
            click.echo("YouTube uploads are disabled in settings. Set YOUTUBE_UPLOAD_ENABLED=true to enable.")
            return

        # Parse tags
        tag_list = []
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]

        # Initialize metadata manager
        metadata_manager = MetadataManager()

        # Generate metadata
        metadata = metadata_manager.generate_metadata(
            video_file=video_file,
            kp_index=kp_index,
            location=location,
            custom_title=title,
            custom_description=description,
            custom_tags=tag_list if tag_list else None
        )

        # Override privacy if specified
        if privacy:
            metadata['privacy_status'] = privacy

        # Validate metadata
        validation = metadata_manager.validate_metadata(metadata)
        if not validation['valid']:
            click.echo("❌ Metadata validation failed:")
            for error in validation['errors']:
                click.echo(f"  - {error}")
            return

        if validation['warnings']:
            click.echo("⚠️  Metadata warnings:")
            for warning in validation['warnings']:
                click.echo(f"  - {warning}")

        click.echo("\n=== Video Metadata ===")
        click.echo(f"Title: {metadata['title']}")
        click.echo(f"Description: {metadata['description'][:200]}...")
        click.echo(f"Tags: {', '.join(metadata['tags'][:10])}{'...' if len(metadata['tags']) > 10 else ''}")
        click.echo(f"Privacy: {metadata['privacy_status']}")

        # Estimate upload time
        time_estimate = metadata_manager.estimate_upload_time(video_file)
        click.echo(f"\n=== Upload Estimate ===")
        click.echo(f"File size: {time_estimate['file_size_formatted']}")
        click.echo(f"Medium speed estimate: {time_estimate['medium']['total_time_formatted']}")

        if dry_run:
            click.echo("\n🔍 Dry run mode - not uploading")
            return

        # Confirm upload
        if not yes and not click.confirm("\nProceed with upload?"):
            click.echo("Upload cancelled.")
            return

        # Initialize uploader
        uploader = YouTubeUploader()

        # Test authentication
        auth_test = uploader.test_authentication()
        if not auth_test['authenticated']:
            click.echo(f"❌ YouTube authentication failed: {auth_test.get('error')}")
            return

        click.echo(f"✅ Authenticated as: {auth_test.get('channel_title', 'Unknown')}")

        # Upload with progress
        click.echo("\nStarting upload...")

        def upload_progress(progress, current, total):
            tqdm.write(f"Upload: {progress:.1f}% ({current:,}/{total:,} bytes)")

        result = uploader.upload_video_with_metadata(
            video_file=video_file,
            metadata=metadata,
            progress_callback=upload_progress
        )

        click.echo(f"\n✅ Upload completed successfully!")
        click.echo(f"Video ID: {result['video_id']}")
        click.echo(f"Video URL: {result['video_url']}")

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument('input_dir', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument('output_file', type=click.Path(path_type=Path))
@click.option('--fps', '-f', type=int, default=None, help='Frames per second')
@click.option('--quality', '-q', type=click.Choice(['low', 'medium', 'high', 'ultra']), default=None, help='Video quality')
@click.option('--kp-threshold', '-t', type=int, default=None, help='Kp index threshold for upload')
@click.option('--force-upload', is_flag=True, help='Upload regardless of Kp threshold')
@click.option('--location', type=str, help='Location for metadata')
@click.option('--thumbnail', is_flag=True, help='Create thumbnail image from middle frame')
@click.option('--progress/--no-progress', default=True, help='Show/hide progress meter')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def process(ctx, input_dir, output_file, fps, quality, kp_threshold, force_upload, location, thumbnail, progress, yes):
    """Complete workflow: generate video and optionally upload based on Kp index."""
    try:
        kp_threshold = kp_threshold or settings.weather.kp_threshold

        click.echo("🎬 Timelapse Generator - Complete Workflow")
        click.echo("=" * 50)

        # Step 1: Check Kp index
        click.echo("\n📡 Step 1: Checking Kp index...")
        client = NOAAClient()
        kp_result = client.check_kp_threshold(kp_threshold)

        if kp_result['threshold_met']:
            click.echo(f"✅ Kp threshold {kp_threshold} met (Max Kp = {kp_result.get('max_kp')})")
            should_upload = True
        else:
            click.echo(f"❌ Kp threshold {kp_threshold} not met (Max Kp = {kp_result.get('max_kp')})")
            should_upload = False

        if force_upload:
            click.echo("⚠️  Force upload enabled - uploading regardless of Kp index")
            should_upload = True

        # Step 2: Generate video
        click.echo("\n🎥 Step 2: Generating video...")
        generator = VideoGenerator(
            fps=fps or settings.video.fps,
            quality=quality or settings.video.quality,
            show_progress=progress
        )

        # Get estimate
        estimate = generator.estimate_output_info(input_dir)
        if "error" in estimate:
            logger.error(f"Failed to estimate output: {estimate['error']}")
            sys.exit(1)

        click.echo(f"Input images: {estimate['input_count']}")
        click.echo(f"Output resolution: {estimate['resolution'][0]}x{estimate['resolution'][1]}")
        click.echo(f"Duration: {estimate['duration_formatted']}")
        click.echo(f"Estimated size: {estimate['estimated_size_mb']:.1f} MB")

        # Generate video
        result = generator.generate_video(input_dir, output_file, create_thumbnail=thumbnail)
        click.echo(f"✅ Video generated: {result['output_path']}")

        # Show thumbnail information if created
        if result.get('thumbnail'):
            thumbnail_info = result['thumbnail']
            click.echo(f"Thumbnail: {thumbnail_info['thumbnail_path']}")
            click.echo(f"Thumbnail size: {thumbnail_info['thumbnail_size_kb']:.1f} KB")

        # Step 3: Upload to YouTube (if applicable)
        if should_upload and settings.youtube.upload_enabled:
            click.echo("\n📺 Step 3: Uploading to YouTube...")

            # Get current Kp index for metadata
            current_kp = kp_result.get('latest_kp') if kp_result.get('threshold_met') else kp_result.get('max_kp')

            # Generate metadata
            metadata_manager = MetadataManager()
            thumbnail_path = None
            if result.get('thumbnail'):
                thumbnail_path = Path(result['thumbnail']['thumbnail_path'])

            metadata = metadata_manager.generate_metadata(
                video_file=output_file,
                kp_index=current_kp,
                location=location,
                thumbnail_path=thumbnail_path
            )

            click.echo(f"Title: {metadata['title']}")

            # Confirm upload
            if yes or click.confirm("Upload to YouTube?"):
                uploader = YouTubeUploader()
                upload_result = uploader.upload_video_with_metadata(output_file, metadata)
                click.echo(f"✅ Upload completed: {upload_result['video_url']}")
            else:
                click.echo("Upload skipped.")

        elif not should_upload:
            click.echo("\n⏭️  Step 3: Skipping upload (Kp threshold not met)")
        else:
            click.echo("\n⏭️  Step 3: Skipping upload (YouTube uploads disabled)")

        click.echo("\n🎉 Workflow completed!")

    except Exception as e:
        logger.error(f"Workflow failed: {e}")
        sys.exit(1)


@cli.command()
def config():
    """Show current configuration."""
    click.echo("📋 Current Configuration")
    click.echo("=" * 30)

    click.echo(f"\n🎥 Video Settings:")
    click.echo(f"  FPS: {settings.video.fps}")
    click.echo(f"  Quality: {settings.video.quality}")
    click.echo(f"  Codec: {settings.video.codec}")
    click.echo(f"  Output Path: {settings.video.output_path}")

    click.echo(f"\n📡 Weather Settings:")
    click.echo(f"  NOAA URL: {settings.weather.noaa_url}")
    click.echo(f"  Kp Threshold: {settings.weather.kp_threshold}")
    click.echo(f"  Cache Duration: {settings.weather.cache_duration}s")

    click.echo(f"\n📺 YouTube Settings:")
    click.echo(f"  Upload Enabled: {settings.youtube.upload_enabled}")
    click.echo(f"  Privacy Status: {settings.youtube.privacy_status}")
    click.echo(f"  Category ID: {settings.youtube.category_id}")
    click.echo(f"  Default Tags: {', '.join(settings.youtube.tags)}")

    click.echo(f"\n📝 Logging Settings:")
    click.echo(f"  Level: {settings.logging.level}")
    click.echo(f"  Log File: {settings.logging.file_path}")


@cli.command()
def backend_info():
    """Show information about available video backends."""
    try:
        from .video.backends import BackendRegistry, list_available_backends

        click.echo("🎥 Video Backend Information\n")

        # Get all backend information
        all_backends = BackendRegistry.get_backend_info()
        available_backends = list_available_backends()

        for name, info in all_backends.items():
            status = "✅ Available" if info['available'] else "❌ Not Available"
            click.echo(f"Backend: {name}")
            click.echo(f"  Status: {status}")
            click.echo(f"  Priority: {info['priority']}")
            click.echo(f"  Default Codec: {info.get('default_codec', 'N/A')}")
            click.echo(f"  Supported Codecs: {', '.join(info.get('supported_codecs', []))}")
            click.echo(f"  Supported Formats: {', '.join(info.get('supported_extensions', []))}")
            click.echo(f"  GPU Support: {'Yes' if info.get('supports_gpu', False) else 'No'}")
            click.echo(f"  Pixel Format: {info.get('pixel_format', 'N/A')}")

            # Show hardware acceleration info for FFmpegCV
            if name == 'ffmpegcv' and info['available']:
                try:
                    from .video.backends.ffmpegcv_backend import FFmpegCVBackend
                    backend = FFmpegCVBackend(30, 1920, 1080)
                    hw_info = backend.get_hardware_info()
                    click.echo(f"  Hardware Acceleration:")
                    click.echo(f"    NVIDIA NVENC: {'Available' if hw_info['nvidia_available'] else 'Not Available'}")
                    click.echo(f"    Intel QSV: {'Available' if hw_info['intel_qsv_available'] else 'Not Available'}")
                    click.echo(f"    AMD AMF: {'Available' if hw_info['amd_available'] else 'Not Available'}")
                except:
                    pass

            click.echo()

        # Show current configuration
        click.echo("📋 Current Configuration:")
        click.echo(f"  Default Backend: {settings.video.backend}")
        click.echo(f"  Auto-Select: {settings.video.auto_select_backend}")
        click.echo(f"  Fallback Enabled: {settings.video.fallback_enabled}")

        click.echo(f"\n🎯 Best Available Backend: {BackendRegistry.get_best_backend() or 'None'}")

        if not available_backends:
            click.echo("\n⚠️  No backends are available! Install dependencies to enable video encoding.")
            click.echo("   For FFmpegCV: pip install ffmpegcv")

    except Exception as e:
        logger.error(f"Failed to get backend info: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()