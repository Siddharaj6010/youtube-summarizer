#!/usr/bin/env python3
"""
YouTube OAuth Refresh Token Setup Script

This is a ONE-TIME setup script that helps you obtain a YouTube OAuth refresh token.
You need this token to allow the YouTube Summarizer to access your YouTube account.

When to run this script:
- First time setting up the YouTube Summarizer
- If your refresh token expires or stops working
- If you want to use a different YouTube account

Prerequisites:
1. Create a Google Cloud project at https://console.cloud.google.com/
2. Enable the YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop application)
4. Download the credentials as client_secret.json
5. Place client_secret.json in this directory or the project root

Usage:
    python scripts/get_refresh_token.py

After running, copy the refresh token to your GitHub repository secrets
as YOUTUBE_REFRESH_TOKEN.
"""

import os
import sys
from pathlib import Path

# Add the project root to the path so we can import from src if needed
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def find_client_secret() -> Path | None:
    """
    Look for client_secret.json in common locations.

    Returns:
        Path to client_secret.json if found, None otherwise.
    """
    # Possible locations for client_secret.json
    possible_paths = [
        Path.cwd() / "client_secret.json",
        Path(__file__).parent / "client_secret.json",
        project_root / "client_secret.json",
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None


def print_missing_credentials_help() -> None:
    """Print instructions for obtaining OAuth credentials."""
    print("""
===========================================
ERROR: client_secret.json not found
===========================================

To get your OAuth credentials:

1. Go to Google Cloud Console:
   https://console.cloud.google.com/

2. Create a new project (or select existing one)

3. Enable the YouTube Data API v3:
   - Go to "APIs & Services" > "Library"
   - Search for "YouTube Data API v3"
   - Click "Enable"

4. Create OAuth credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Desktop application"
   - Give it a name (e.g., "YouTube Summarizer")
   - Click "Create"

5. Download the credentials:
   - Click the download button (JSON)
   - Rename the file to "client_secret.json"
   - Place it in one of these locations:
     - Current directory
     - scripts/ directory
     - Project root directory

6. Run this script again:
   python scripts/get_refresh_token.py

===========================================
""")


def print_header() -> None:
    """Print the script header."""
    print("""
===========================================
YouTube OAuth Setup
===========================================
""")


def main() -> int:
    """
    Main entry point for the OAuth setup script.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    print_header()

    # Try to import the required library
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("""
ERROR: Required library not installed.

Please install the required dependencies:
    pip install google-auth-oauthlib

Or if using the project:
    pip install -e ".[dev]"
""")
        return 1

    print("Looking for client_secret.json...")

    client_secret_path = find_client_secret()

    if client_secret_path is None:
        print_missing_credentials_help()
        return 1

    print(f"Found: {client_secret_path}")
    print()

    # Define the OAuth scopes we need
    scopes = [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube",
    ]

    print("Opening browser for authorization...")
    print("(If browser doesn't open, check the terminal for a URL to visit manually)")
    print()

    try:
        # Create the OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path),
            scopes=scopes,
        )

        # Run the local server flow
        # This will open a browser window for the user to authorize
        credentials = flow.run_local_server(
            port=8080,
            prompt="consent",
            access_type="offline",  # This is what gives us a refresh token
        )

    except FileNotFoundError:
        print(f"ERROR: Could not read {client_secret_path}")
        print("Make sure the file exists and is readable.")
        return 1

    except KeyboardInterrupt:
        print("\n\nAuthorization cancelled by user.")
        return 1

    except Exception as e:
        error_msg = str(e).lower()

        if "access_denied" in error_msg or "cancelled" in error_msg:
            print("""
===========================================
Authorization Cancelled
===========================================

You cancelled the authorization or denied access.
Run this script again when you're ready to authorize.
""")
            return 1

        if "connection" in error_msg or "network" in error_msg:
            print(f"""
===========================================
Network Error
===========================================

Could not complete authorization due to a network error:
{e}

Please check your internet connection and try again.
""")
            return 1

        # Unknown error
        print(f"""
===========================================
Error During Authorization
===========================================

An error occurred: {e}

If this persists, try:
1. Deleting any cached credentials
2. Re-downloading client_secret.json from Google Cloud Console
3. Making sure your OAuth consent screen is configured
""")
        return 1

    # Check if we got a refresh token
    if not credentials.refresh_token:
        print("""
===========================================
WARNING: No Refresh Token Received
===========================================

The authorization succeeded but no refresh token was provided.
This can happen if you've already authorized this app before.

To get a new refresh token:
1. Go to https://myaccount.google.com/permissions
2. Find and remove access for your OAuth app
3. Run this script again

""")
        return 1

    # Success! Print the refresh token
    print("""
Authorization successful!

===========================================
YOUR REFRESH TOKEN (copy this to GitHub Secrets):
===========================================
""")
    print(credentials.refresh_token)
    print("""
===========================================
Next steps:
1. Go to your GitHub repo -> Settings -> Secrets -> Actions
2. Create a new secret named: YOUTUBE_REFRESH_TOKEN
3. Paste the token above as the value
4. Delete client_secret.json (don't commit it to git!)
===========================================
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
