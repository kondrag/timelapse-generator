# Enhanced Progress Meter Feature

## Overview

The timelapse generator includes a sophisticated progress meter that provides real-time feedback during video creation. This feature helps users monitor the processing progress, performance metrics, and estimated completion time.

## Features

### Real-time Statistics
- **Percentage Completion**: Visual progress bar with precise percentage
- **Frame Counting**: Processed frames vs total frames (frames: 167/250)
- **Success Rate**: Percentage of successfully processed images (success: 99%)
- **Processing Speed**: Images processed per second (fps: 1.9)
- **Video Duration**: Current video length in seconds (video: 5.6s)
- **ETA**: Estimated time remaining in seconds (eta: 42s)
- **Skipped Frames**: Count of invalid/corrupted images (shown only when applicable)

### Progress Bar Format
```
Creating timelapse: 67%|███████████████████████████████████████████▌| 168/250 [01:23<00:42, 1.97it/s]
frames: 167/250, success: 99%, fps: 1.9, video: 5.6s, eta: 42s
```

## Usage

### Command Line Options

#### Show Progress (Default)
```bash
timelapse generate /path/to/images output.mp4 --progress
# or simply (progress is shown by default)
timelapse generate /path/to/images output.mp4
```

#### Hide Progress
```bash
timelapse generate /path/to/images output.mp4 --no-progress
```

#### Complete Workflow with Progress Control
```bash
timelapse process /path/to/images output.mp4 --no-progress --thumbnail
```

## Implementation Details

### Performance Metrics
- **Images per Second**: Processing speed calculated from elapsed time
- **Success Rate**: Percentage of valid images processed successfully
- **ETA Calculation**: Based on current processing speed and remaining images
- **Dynamic Updates**: Statistics update in real-time during processing

### Error Handling
- **Skipped Frames**: Automatically tracks and displays count of invalid images
- **Success Rate Monitoring**: Shows processing reliability percentage
- **Graceful Degradation**: Progress meter handles errors without interrupting processing

### Customization Options
- **Toggle Progress**: `--progress/--no-progress` flags
- **Dynamic Column Width**: Progress bar adapts to terminal width
- **Conditional Display**: Skipped count only shown when frames are skipped

## Code Architecture

### Progress Tracking Class
The `VideoGenerator` class includes:
- `show_progress` parameter for progress control
- `update_progress_info()` method for display updates
- Timing and statistics calculation
- Error tracking and reporting

### Progress Information Flow
1. **Initialization**: Setup progress context and initial state
2. **Processing Loop**: Update metrics after each image processed
3. **Statistics Calculation**: Compute rates, ETA, and success percentages
4. **Display Updates**: Refresh progress bar with current statistics
5. **Final Report**: Log completion statistics

### Key Methods
```python
def update_progress_info(frames_processed, total_frames, skips, fps_rate=None, video_duration=None, eta_seconds=None):
    """Update progress display with current statistics."""
```

## Performance Considerations

### Efficiency
- **Minimal Overhead**: Progress tracking adds minimal processing time
- **Smart Updates**: Only updates display when meaningful changes occur
- **Error Resilience**: Progress continues even if display updates fail

### Resource Usage
- **Memory Efficient**: Tracks only essential statistics
- **CPU Light**: Minimal computational overhead for progress calculations
- **Terminal Friendly**: Adapts to different terminal widths and capabilities

## User Experience

### Visual Feedback
- **Immediate Response**: Progress appears immediately upon processing start
- **Clear Metrics**: Easy-to-understand statistics and time estimates
- **Error Visibility**: Skipped frames and processing issues clearly shown

### Progress Validation
- **Completion Verification**: Final statistics confirm processing success
- **Quality Assurance**: Success rate helps identify image quality issues
- **Performance Monitoring**: Processing speed helps optimize workflows

## Configuration

### Default Behavior
- **Progress Enabled**: Shows progress meter by default
- **Auto-Sizing**: Progress bar adapts to terminal width
- **Smart Display**: Conditional information display based on context

### Environment Variables
Future enhancements could include:
- `TIMELAPSE_NO_PROGRESS`: Environment variable to disable progress
- `TIMELAPSE_PROGRESS_STYLE`: Custom progress display formats
- `TIMELAPSE_UPDATE_INTERVAL`: Control update frequency

## Future Enhancements

Potential improvements could include:
- **Detailed Statistics**: More granular performance metrics
- **Custom Formats**: User-configurable progress display formats
- **Export Progress**: Save progress data to file
- **Remote Monitoring**: Progress updates via web interface or API
- **Performance Profiles**: Pre-configured progress display styles

## Troubleshooting

### Common Issues
- **Terminal Width**: Progress bar adapts to narrow terminals
- **Display Glitches**: Automatic recovery from display issues
- **Performance Impact**: Minimal overhead on most systems

### Debug Information
- **Verbose Logging**: Use `--verbose` flag for detailed progress information
- **Statistics Export**: Progress data can be logged for analysis
- **Error Tracking**: Skipped frame details logged for debugging

## Examples

### Basic Usage
```bash
# Generate with progress (default)
timelapse generate /path/to/images output.mp4

# Generate without progress for clean output
timelapse generate /path/to/images output.mp4 --no-progress

# Complete workflow with controlled progress
timelapse process /path/to/images output.mp4 --progress --thumbnail --kp-threshold 4
```

### Sample Output
```
🎬 Timelapse Generator - Complete Workflow
==================================================

📡 Step 1: Checking Kp index...
✅ Kp threshold 4 met (Max Kp = 5.2)

🎥 Step 2: Generating video...
Input images: 500
Output resolution: 1920x1080
Duration: 00:16
Estimated size: 125.3 MB

Creating timelapse: 100%|████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 500/500 [02:45<00:00, 3.02it/s]
frames: 498/500, success: 99%, fps: 3.0, video: 16.6s, eta: 0s

✅ Video generated: /path/to/output/timelapse.mp4
Thumbnail: /path/to/output/timelapse_thumbnail.jpg
Thumbnail size: 245.7 KB
```