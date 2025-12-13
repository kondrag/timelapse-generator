#!/usr/bin/env python3
"""
Setup script for YouTube authentication.

This script helps users set up YouTube API credentials for the timelapse generator.
"""

import os
import sys
from pathlib import Path

def main():
    """Main setup script."""
    print("🎬 Timelapse Generator - YouTube Authentication Setup")
    print("=" * 60)

    # Check if credentials file already exists
    credentials_file = Path("youtube_credentials.json")
    if credentials_file.exists():
        print(f"⚠️  Credentials file already exists: {credentials_file}")
        response = input("Do you want to recreate it? (y/N): ").strip().lower()
        if response != 'y':
            print("Setup cancelled.")
            return

    print("\n📋 Step 1: Create Google Cloud Project")
    print("-" * 40)
    print("1. Go to: https://console.cloud.google.com/")
    print("2. Create a new project or select an existing one")
    print("3. Enable the 'YouTube Data API v3'")
    print("4. Go to 'Credentials' in the sidebar")
    print("5. Click 'Create Credentials' → 'OAuth 2.0 Client ID'")
    print("6. Configure consent screen if prompted")
    print("7. Select 'Desktop app' as application type")
    print("8. Download the JSON file and save it as 'youtube_credentials.json'")

    input("\nPress Enter when you have completed these steps...")

    # Verify credentials file exists
    if not credentials_file.exists():
        print(f"\n❌ Credentials file not found: {credentials_file}")
        print("Please make sure you've downloaded and saved the credentials file correctly.")
        sys.exit(1)

    print(f"\n✅ Credentials file found: {credentials_file}")

    # Test authentication
    print("\n📋 Step 2: Test Authentication")
    print("-" * 40)
    print("The script will now test your YouTube authentication.")
    print("A browser window will open asking you to authorize the application.")

    try:
        # Import here to avoid dependency issues during setup
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from timelapse_generator.youtube.uploader import YouTubeUploader

        uploader = YouTubeUploader()
        auth_result = uploader.test_authentication()

        if auth_result['authenticated']:
            print(f"\n✅ Authentication successful!")
            print(f"Channel: {auth_result.get('channel_title', 'Unknown')}")
            print(f"Channel ID: {auth_result.get('channel_id', 'Unknown')}")
        else:
            print(f"\n❌ Authentication failed: {auth_result.get('error', 'Unknown error')}")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Authentication test failed: {e}")
        print("\nPlease check:")
        print("1. Your credentials file is valid JSON")
        print("2. YouTube Data API v3 is enabled")
        print("3. OAuth consent screen is configured")
        print("4. Network connectivity")
        sys.exit(1)

    # Environment setup
    print("\n📋 Step 3: Environment Setup")
    print("-" * 40)

    env_file = Path(".env")
    env_vars = []

    # Check if YouTube uploads should be enabled
    enable_uploads = input("Enable YouTube uploads by default? (Y/n): ").strip().lower()
    if enable_uploads != 'n':
        env_vars.append("YOUTUBE_UPLOAD_ENABLED=true")

    # Check for custom Kp threshold
    kp_threshold = input("Set Kp index threshold (default 4): ").strip()
    if kp_threshold and kp_threshold.isdigit():
        env_vars.append(f"KP_THRESHOLD={kp_threshold}")

    # Create .env file
    if env_vars:
        if env_file.exists():
            print(f"\n⚠️  .env file already exists. New variables will be appended.")

        with open(env_file, 'a') as f:
            f.write("\n# Timelapse Generator Configuration\n")
            for var in env_vars:
                f.write(f"{var}\n")

        print(f"✅ Environment variables added to {env_file}")

    # Final instructions
    print("\n🎉 Setup Complete!")
    print("=" * 30)
    print("\nYou can now use the timelapse generator with YouTube integration:")
    print("\n  timelapse upload your_video.mp4 --dry-run")
    print("  timelapse process /path/to/images output.mp4 --kp-threshold 4")
    print("\nFor more help:")
    print("  timelapse --help")
    print("  timelapse upload --help")
    print("  timelapse process --help")

    print(f"\nConfiguration files:")
    print(f"  - Credentials: {credentials_file.absolute()}")
    print(f"  - Environment: {env_file.absolute() if env_file.exists() else 'None'}")


if __name__ == "__main__":
    main()