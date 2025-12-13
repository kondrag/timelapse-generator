"""YouTube video uploader."""

import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ..config.settings import settings
from ..config.templates import templates
from ..utils.logging import get_logger
from ..utils.retry import retry

logger = get_logger(__name__)


class YouTubeUploader:
    """Upload videos to YouTube using the YouTube Data API."""

    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    API_SERVICE_NAME = 'youtube'
    API_VERSION = 'v3'

    def __init__(self, credentials_file: Optional[Path] = None, token_file: Optional[Path] = None):
        """Initialize YouTube uploader.

        Args:
            credentials_file: Path to OAuth2 credentials JSON file
            token_file: Path to store OAuth2 token
        """
        self.credentials_file = credentials_file or Path("youtube_credentials.json")
        self.token_file = token_file or Path.home() / ".cache" / "timelapse_generator" / "youtube_token.json"

        self.token_file.parent.mkdir(parents=True, exist_ok=True)

        self.youtube_service = None
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with YouTube API."""
        logger.info("Authenticating with YouTube API")

        credentials = None

        # Load existing token if available
        if self.token_file.exists():
            try:
                from google.oauth2.credentials import Credentials
                credentials = Credentials.from_authorized_user_file(str(self.token_file), self.SCOPES)
                logger.debug("Loaded existing YouTube credentials")
            except Exception as e:
                logger.warning(f"Failed to load existing credentials: {e}")

        # If credentials are invalid or missing, get new ones
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    logger.info("Refreshed expired credentials")
                except Exception as e:
                    logger.warning(f"Failed to refresh credentials: {e}")
                    credentials = None

            if not credentials:
                credentials = self._get_new_credentials()

            # Save credentials for next run
            try:
                with open(self.token_file, 'w') as token:
                    token.write(credentials.to_json())
                logger.info(f"Saved credentials to {self.token_file}")
            except Exception as e:
                logger.error(f"Failed to save credentials: {e}")

        # Build YouTube service
        try:
            self.youtube_service = build(
                self.API_SERVICE_NAME,
                self.API_VERSION,
                credentials=credentials,
                static_discovery=False
            )
            logger.info("YouTube API service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to build YouTube service: {e}")
            raise

    def _get_new_credentials(self):
        """Get new OAuth2 credentials."""
        if not self.credentials_file.exists():
            raise FileNotFoundError(
                f"YouTube credentials file not found: {self.credentials_file}\n"
                "Please create a YouTube Data API v3 project and download the credentials JSON file.\n"
                "See: https://developers.google.com/youtube/v3/getting-started"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.credentials_file),
            self.SCOPES
        )

        logger.info("Opening browser for OAuth authentication...")
        return flow.run_local_server(port=0)

    @retry((HttpError, ConnectionError), max_attempts=3, delay=5.0)
    def upload_video(
        self,
        video_file: Path,
        title: str,
        description: str,
        tags: list,
        privacy_status: Optional[str] = None,
        category_id: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Upload a video to YouTube.

        Args:
            video_file: Path to video file
            title: Video title
            description: Video description
            tags: Video tags
            privacy_status: Privacy status (public, unlisted, private)
            category_id: YouTube category ID
            progress_callback: Callback for upload progress

        Returns:
            Dictionary with upload results

        Raises:
            FileNotFoundError: If video file doesn't exist
            HttpError: If YouTube API request fails
        """
        if not video_file.exists():
            raise FileNotFoundError(f"Video file not found: {video_file}")

        if not self.youtube_service:
            raise RuntimeError("YouTube service not initialized")

        # Use settings defaults if not provided
        if privacy_status is None:
            privacy_status = settings.youtube.privacy_status
        if category_id is None:
            category_id = settings.youtube.category_id

        logger.info(f"Starting YouTube upload: {video_file}")

        # Prepare request body
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy_status
            }
        }

        # Prepare media upload
        media = MediaFileUpload(
            str(video_file),
            chunksize=-1,  # Resumable upload
            resumable=True
        )

        # Create upload request
        request = self.youtube_service.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        # Execute upload with progress tracking
        response = None
        error = None
        retry_count = 0
        max_retries = 3

        while response is None and retry_count < max_retries:
            try:
                logger.info(f"Upload attempt {retry_count + 1}/{max_retries}")
                status, response = request.next_chunk()

                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"Upload progress: {progress}%")

                    if progress_callback:
                        progress_callback(progress, status.resumable_progress, status.total_size)

            except HttpError as e:
                error = e
                logger.error(f"Upload failed (attempt {retry_count + 1}): {e}")
                retry_count += 1

                if retry_count < max_retries:
                    logger.info(f"Retrying upload in {5 * retry_count} seconds...")
                    time.sleep(5 * retry_count)

        if response is None:
            logger.error("Upload failed after all retries")
            if error:
                raise error
            else:
                raise RuntimeError("Upload failed for unknown reason")

        # Extract video information
        video_id = response.get('id')
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        logger.info(f"Upload completed successfully: {video_url}")

        return {
            "success": True,
            "video_id": video_id,
            "video_url": video_url,
            "title": title,
            "privacy_status": privacy_status,
            "upload_response": response
        }

    def upload_video_with_metadata(
        self,
        video_file: Path,
        metadata: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Upload video with metadata dictionary.

        Args:
            video_file: Path to video file
            metadata: Metadata dictionary with title, description, tags
            **kwargs: Additional upload parameters

        Returns:
            Dictionary with upload results
        """
        return self.upload_video(
            video_file=video_file,
            title=metadata.get("title", "Timelapse Video"),
            description=metadata.get("description", ""),
            tags=metadata.get("tags", []),
            **kwargs
        )

    def get_quota_usage(self) -> Dict[str, Any]:
        """Get current YouTube API quota usage.

        Returns:
            Dictionary with quota information
        """
        try:
            # This is a rough estimate - YouTube doesn't provide precise quota info
            # through the API. Actual quota depends on various factors.
            quota_info = {
                "daily_limit": "10,000 units",
                "upload_cost": "1,600 units per video upload",
                "note": "Exact quota usage not available through API"
            }
            return quota_info

        except Exception as e:
            logger.error(f"Failed to get quota usage: {e}")
            return {"error": str(e)}

    def test_authentication(self) -> Dict[str, Any]:
        """Test YouTube API authentication.

        Returns:
            Dictionary with authentication status
        """
        try:
            if not self.youtube_service:
                return {
                    "authenticated": False,
                    "error": "YouTube service not initialized"
                }

            # Try to access the authenticated user's channel
            response = self.youtube_service.channels().list(
                part="snippet",
                mine=True
            ).execute()

            if response.get("items"):
                channel = response["items"][0]
                return {
                    "authenticated": True,
                    "channel_id": channel["id"],
                    "channel_title": channel["snippet"]["title"],
                    "channel_description": channel["snippet"].get("description", "")
                }
            else:
                return {
                    "authenticated": False,
                    "error": "No channel found for authenticated user"
                }

        except Exception as e:
            return {
                "authenticated": False,
                "error": str(e)
            }

    def revoke_credentials(self) -> bool:
        """Revoke stored credentials.

        Returns:
            True if successful
        """
        try:
            if self.token_file.exists():
                self.token_file.unlink()
                logger.info("Revoked YouTube credentials")
            return True

        except Exception as e:
            logger.error(f"Failed to revoke credentials: {e}")
            return False