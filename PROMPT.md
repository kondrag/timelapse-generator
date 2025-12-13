Timelapse Generator

=====

You are an expert Python developer.  Let's create an commandline Python application that will create timelapse video of the night sky from a collection of images and optionally upload the resulting video to YouTube.  The images will be in JPEG format and have names with timestamps in them, so they are easily sortable from oldest to newest.  The application needs to support several features.

- Generate a timelapse video from a directory of images.  The video encoding should have options for quality, resolution, and output filename.
- Check the NOAA SpaceWeather website at https://www.swpc.noaa.gov/products/solar-and-geophysical-activity-summary for the latest observed Kp index.
- If the Kp index overnight was 4 or higher, upload the video to YouTube.  The video upload should support a template of video metadata to upload with the file and support dynamic updating of the metadata fields.

The target system is Linux.  The implementation language should be Python and use UV for dependency management.