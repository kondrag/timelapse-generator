# Timelapse Generator

A Python command-line application that creates timelapse videos from night sky images and automatically uploads them to YouTube when the Kp index indicates aurora activity.

## Features

- 🎥 **Video Generation**: Create timelapse videos from JPEG image sequences
- 🖼️ **Thumbnail Generation**: Automatically create thumbnails from middle frames
- 📊 **Enhanced Progress Meter**: Real-time processing statistics and ETA
- 📡 **Kp Index Monitoring**: Check NOAA SpaceWeather for geomagnetic activity
- 📺 **YouTube Integration**: Automatic uploads with dynamic metadata
- ⚙️ **Configurable**: Flexible settings for quality, resolution, and output
- 🎯 **Smart Metadata**: Templates that incorporate Kp index and other data
- 📝 **Logging**: Comprehensive logging with configurable levels

## Installation

### Prerequisites

- Python 3.9 or higher
- [UV](https://github.com/astral-sh/uv) package manager
- OpenCV system dependencies
- FFmpeg (optional but recommended)

### System Dependencies

On Ubuntu/Debian:
```bash
sudo apt update
sudo apt install python3-opencv ffmpeg
```

On Fedora:
```bash
sudo dnf install opencv-python ffmpeg
```

### Install with UV

```bash
# Clone the repository
git clone https://github.com/yourusername/timelapse_generator.git
cd timelapse_generator

# Install with UV
uv sync

# Install development dependencies (optional)
uv sync --dev
```

## Quick Start

### 1. Initial Setup

```bash
# Create default configuration
timelapse config

# Test YouTube authentication (optional)
timelapse upload --dry-run your_video.mp4
```

### 2. Generate a Timelapse

```bash
# Basic video generation
timelapse generate /path/to/images output_video.mp4

# With custom settings
timelapse generate /path/to/images output_video.mp4 --fps 30 --quality high --resolution 1920x1080

# Create a thumbnail from the middle frame
timelapse generate /path/to/images output_video.mp4 --thumbnail

# Generate without progress meter for cleaner output
timelapse generate /path/to/images output_video.mp4 --no-progress
```

### 3. Check Kp Index

```bash
# Check current Kp index
timelapse check-kp --threshold 4

# Skip cached data
timelapse check-kp --no-cache
```

### 4. Complete Workflow

```bash
# Generate video and upload if Kp ≥ 4
timelapse process /path/to/images output_video.mp4 --kp-threshold 4 --location "Your Location"

# Force upload regardless of Kp
timelapse process /path/to/images output_video.mp4 --force-upload
```

## Configuration

### Environment Variables

```bash
# YouTube integration
export YOUTUBE_UPLOAD_ENABLED=true
export YOUTUBE_CREDENTIALS_FILE="path/to/credentials.json"

# Kp threshold
export KP_THRESHOLD=4

# Custom configuration file
export TIMELAPSE_CONFIG="config.yaml"
```

### Configuration File

Create a `config.yaml` file:

```yaml
video:
  fps: 30
  quality: "medium"
  codec: "mp4v"
  output_path: "./output"
  bitrate: "5M"
  resolution: [1920, 1080]

weather:
  noaa_url: "https://www.swpc.noaa.gov/products/solar-and-geophysical-activity-summary"
  kp_threshold: 4
  cache_duration: 3600
  retry_attempts: 3
  retry_delay: 5

youtube:
  upload_enabled: false
  privacy_status: "private"
  category_id: "22"
  tags: ["timelapse", "astrophotography", "night sky"]

logging:
  level: "INFO"
  file_path: null
  max_file_size: 10485760
  backup_count: 5
```

## YouTube Setup

### 1. Create YouTube API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the YouTube Data API v3
4. Create OAuth 2.0 Client ID credentials
5. Download the JSON credentials file

### 2. Configure Authentication

```bash
# Place credentials file in project root
cp ~/Downloads/client_secret_*.json youtube_credentials.json

# Test authentication
timelapse upload --dry-run your_video.mp4
```

## Usage Examples

### Video Generation Options

```bash
# Estimate output size only
timelapse generate /path/to/images output.mp4 --estimate-only

# High quality with custom codec
timelapse generate /path/to/images output.mp4 --quality high --codec x264

# Custom resolution
timelapse generate /path/to/images output.mp4 --resolution 3840x2160

# Create thumbnail with video
timelapse generate /path/to/images output.mp4 --thumbnail --quality high
```

### Thumbnail Generation

When using the `--thumbnail` flag, the application will:
- Select the middle image from the sequence
- Resize it to match the video output resolution
- Save it as `[video_name]_thumbnail.[ext]` in the same directory as the video
- Use high-quality JPEG (95%) or PNG compression based on input format
- Display thumbnail information after generation

Example output:
```
Thumbnail: /path/to/output/timelapse_thumbnail.jpg
Thumbnail size: 245.7 KB
Source image: IMG_20231201_220000.jpg
Middle frame: 125/250
```

### Enhanced Progress Meter

The application includes a detailed progress meter that shows real-time processing information:

- **Percentage Complete**: Visual progress bar with percentage
- **Frames Processed**: Current frames processed vs total frames
- **Success Rate**: Percentage of successfully processed images
- **Processing Speed**: Images processed per second
- **Video Duration**: Current video length in seconds
- **ETA**: Estimated time remaining
- **Skipped Frames**: Count of invalid/corrupted images (shown only when applicable)

Example progress output:
```
Creating timelapse: 67%|███████████████████████████████████████████▌| 168/250 [01:23<00:42, 1.97it/s]
frames: 167/250, success: 99%, fps: 1.9, video: 5.6s, eta: 42s
```

**Progress Control:**
- Use `--progress` (default) to show the enhanced progress meter
- Use `--no-progress` to hide the progress bar for cleaner output

### YouTube Upload Options

```bash
# Custom metadata
timelapse upload video.mp4 --title "My Aurora Timelapse" --description "Amazing aurora display" --tags "aurora,northernlights"

# Public upload
timelapse upload video.mp4 --privacy public --location "Fairbanks, Alaska"

# Include Kp index in metadata
timelapse upload video.mp4 --kp-index 6.5
```

### Advanced Workflow

```bash
# Complete workflow with custom settings
timelapse process /path/to/images output.mp4 \
  --fps 25 \
  --quality high \
  --resolution 1920x1080 \
  --kp-threshold 5 \
  --location "Your City, Country" \
  --thumbnail

# Monitor Kp index continuously
while true; do
  timelapse check-kp --threshold 4
  sleep 3600  # Check every hour
done
```

## File Organization

### Input Images

Images should be named with timestamps for proper sorting:
```
images/
├── IMG_20231201_200000.jpg
├── IMG_20231201_201000.jpg
├── IMG_20231201_202000.jpg
└── ...
```

Supported formats:
- JPEG (.jpg, .jpeg, .JPG, .JPEG)
- PNG (.png, .PNG)

### Output Structure

```
project/
├── config.yaml
├── youtube_credentials.json
├── images/
├── output/
│   └── timelapse_20231201.mp4
└── .cache/
    └── timelapse_generator/
        ├── noaa_cache.json
        ├── kp_data.db
        └── youtube_token.json
```

## Templates

Customize YouTube metadata templates in the `templates/` directory:

### Title Template (`templates/title.j2`)
```jinja2
Aurora Timelapse - {{ date | format_date('%B %d, %Y') }}{% if kp_index %} (Kp {{ kp_index | format_kp }}){% endif %}
```

### Description Template (`templates/description.j2`)
```jinja2
Night sky timelapse captured on {{ date | format_date('%B %d, %Y') }}{% if location %} from {{ location }}{% endif %}.

{% if kp_index %}Space Weather Activity:
- Kp Index: {{ kp_index | format_kp }}
- Geomagnetic conditions: {% if kp_index >= 5 %}Storm{% elif kp_index >= 4 %}Active{% else %}Quiet{% endif %}
{% endif %}
```

## Troubleshooting

### Common Issues

**No images found**
```bash
# Check image naming and format
ls -la /path/to/images/*.jpg
```

**YouTube authentication fails**
```bash
# Check credentials file
cat youtube_credentials.json

# Test authentication
timelapse upload --dry-run test.mp4
```

**Kp index not updating**
```bash
# Clear cache and retry
rm -rf ~/.cache/timelapse_generator/
timelapse check-kp --no-cache
```

### Debug Mode

Enable verbose logging:
```bash
timelapse --verbose generate /path/to/images output.mp4
```

### Logs

Check application logs:
```bash
# Default log location
tail -f ~/.cache/timelapse_generator/timelapse.log

# Custom log file
timelapse --log-file debug.log --verbose generate /path/to/images output.mp4
```

## Development

### Setup Development Environment

```bash
# Install development dependencies
uv sync --dev

# Run tests
uv run pytest

# Code formatting
uv run black src/
uv run flake8 src/

# Type checking
uv run mypy src/
```

### Project Structure

```
src/timelapse_generator/
├── cli.py                 # Command line interface
├── config/
│   ├── settings.py        # Configuration management
│   └── templates.py       # Metadata templates
├── video/
│   ├── generator.py       # Video generation
│   └── encoder.py         # Video encoding
├── weather/
│   ├── noaa_client.py     # NOAA data fetching
│   └── kp_parser.py       # Kp index parsing
├── youtube/
│   ├── uploader.py        # YouTube uploads
│   └── metadata.py        # Metadata management
└── utils/
    ├── file_utils.py      # File operations
    ├── logging.py         # Logging setup
    └── retry.py           # Retry utilities
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Support

- 📖 Documentation: [Project Wiki](https://github.com/yourusername/timelapse_generator/wiki)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/timelapse_generator/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/yourusername/timelapse_generator/discussions)

## Acknowledgments

- NOAA Space Weather Prediction Center for Kp index data
- Google YouTube Data API
- OpenCV community
- All contributors and users of this project