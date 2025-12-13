# Thumbnail Generation Feature

## Overview

The timelapse generator now supports automatic thumbnail creation from the middle frame of the image sequence. This feature helps create representative preview images for timelapse videos.

## Usage

### Generate Command
```bash
# Create video with thumbnail
timelapse generate /path/to/images output.mp4 --thumbnail

# Complete workflow with thumbnail
timelapse process /path/to/images output.mp4 --thumbnail --kp-threshold 4
```

## Implementation Details

### Feature Behavior
1. **Middle Frame Selection**: Automatically selects the image closest to the middle of the sequence
2. **Resolution Matching**: Resizes thumbnail to match the output video resolution
3. **High Quality**: Uses 95% JPEG quality or optimized PNG based on input format
4. **Smart Naming**: Creates `[video_name]_thumbnail.[ext]` in the same directory
5. **Fallback Support**: Uses OpenCV if PIL is not available

### Technical Implementation

#### Video Generator Updates
- Added `create_thumbnail` parameter to `generate_video()` method
- Implemented `_create_thumbnail()` method for thumbnail processing
- Returns thumbnail information in the result dictionary

#### CLI Integration
- Added `--thumbnail` flag to `generate` and `process` commands
- Displays thumbnail information after video generation
- Includes thumbnail path, size, and source image details

#### YouTube Integration
- Passes thumbnail information to metadata generation
- Templates can access thumbnail-related variables:
  - `has_thumbnail`: Boolean indicating if thumbnail exists
  - `thumbnail_filename`: Name of the thumbnail file

### Output Example
```
✅ Video generated successfully!
Output: /path/to/output/timelapse.mp4
Frames processed: 250
Frames skipped: 0
Output size: 45.2 MB
Duration: 8.3 seconds
Resolution: 1920x1080
Thumbnail: /path/to/output/timelapse_thumbnail.jpg
Thumbnail size: 245.7 KB
Source image: IMG_20231201_220000.jpg
Middle frame: 125/250
```

### File Structure Example
```
output/
├── timelapse.mp4           # Generated video
└── timelapse_thumbnail.jpg # Generated thumbnail
```

## Code Changes

### Core Changes
1. **VideoGenerator.generate_video()**: Added `create_thumbnail` parameter
2. **VideoGenerator._create_thumbnail()**: New method for thumbnail creation
3. **CLI commands**: Added `--thumbnail` flag to relevant commands
4. **Metadata generation**: Enhanced to include thumbnail information

### Dependencies
- Uses PIL (Pillow) for high-quality image saving when available
- Falls back to OpenCV for compatibility
- Supports JPEG and PNG input formats

## Benefits

1. **Preview Images**: Provides instant preview of timelapse content
2. **Social Media**: Ready-to-use thumbnails for sharing
3. **YouTube Ready**: Thumbnails can be used for custom YouTube thumbnails
4. **Quality Assurance**: High-resolution thumbnails matching video quality
5. **Automation**: No manual image selection or processing required

## Error Handling

- Gracefully handles missing or invalid middle images
- Logs detailed information about thumbnail creation process
- Continues video generation even if thumbnail creation fails
- Validates thumbnail file creation before reporting success

## Future Enhancements

Potential future improvements could include:
- Custom thumbnail position selection (not just middle)
- Multiple thumbnail generation
- Thumbnail effects and text overlay
- Direct YouTube thumbnail upload
- Custom thumbnail naming patterns