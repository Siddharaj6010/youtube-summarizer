# YouTube Video Summarizer - Implementation Plan

An automated system that summarizes YouTube videos and saves them to Notion.

## Overview

When you add a video to a YouTube playlist, this automation will:
1. Detect the new video
2. Fetch its transcript
3. Generate an AI summary using Claude Haiku
4. Save the summary to Notion
5. Move the video to a "Summarized" playlist

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              YOUR WORKFLOW                               │
│                                                                          │
│   See video → Add to "📥 To Summarize" → Forget about it                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         AUTOMATION (every 15 min)                        │
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │ 📥 To        │    │   Process    │    │ ✅ Summarized │               │
│  │ Summarize    │───▶│   Video      │───▶│   Playlist    │               │
│  │ Playlist     │    │              │    │               │               │
│  └──────────────┘    └──────┬───────┘    └──────────────┘               │
│         │                   │                    ▲                       │
│         │                   ▼                    │                       │
│         │           ┌──────────────┐             │                       │
│         │           │    Notion    │             │                       │
│         │           │   Database   │             │                       │
│         │           └──────────────┘             │                       │
│         │                                        │                       │
│         └───────────── MOVE VIDEO ───────────────┘                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## System Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         GitHub Actions (Free)                           │
│                         Runs every 15 minutes                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Python Script                                  │
│                                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────┐ │
│  │   YouTube   │───▶│  Transcript │───▶│   Claude    │───▶│  Notion  │ │
│  │   Data API  │    │   Fetcher   │    │   Haiku     │    │   API    │ │
│  └─────────────┘    └─────────────┘    └─────────────┘    └──────────┘ │
│        │                                                        │       │
│        │              "Already processed"                       │       │
│        └──────────────── video IDs ◄────────────────────────────┘       │
│                     (stored in Notion)                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Step 1: FETCH PLAYLIST
────────────────────────────────────────────────────
    YouTube API                Your Playlist
    ───────────                "📥 To Summarize"
         │                           │
         │   GET playlist items      │
         │◄──────────────────────────│
         │                           │
         │   Returns: [              │
         │     {videoId: "abc123"},  │
         │     {videoId: "def456"},  │
         │   ]                       │
         ▼

Step 2: FILTER NEW VIDEOS
────────────────────────────────────────────────────
    Python Script              Notion Database
    ─────────────              ────────────────
         │                           │
         │   Query: all video IDs    │
         │──────────────────────────▶│
         │                           │
         │   Returns: ["abc123"]     │  (already done)
         │◄──────────────────────────│
         │                           │
         │   New videos = ["def456"] │
         ▼

Step 3: PROCESS EACH NEW VIDEO
────────────────────────────────────────────────────
    For video "def456":

    ┌──────────────────┐
    │ youtube-transcript│    GET captions
    │       -api        │───────────────────▶ YouTube
    │    (free lib)     │◄─────────────────── (transcript text)
    └────────┬─────────┘
             │ transcript
             ▼
    ┌──────────────────┐
    │   Claude Haiku   │    "Summarize this..."
    │   (~$0.002)      │───────────────────▶ Anthropic API
    │                  │◄─────────────────── (summary)
    └────────┬─────────┘
             │ summary
             ▼
    ┌──────────────────┐
    │   Notion API     │    Create page
    │   (free)         │───────────────────▶ Your Database
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │   YouTube API    │    Move video
    │   (OAuth)        │───────────────────▶ To "✅ Summarized"
    └──────────────────┘
```

## Project Structure

```
youtube-summarizer/
│
├── .github/
│   └── workflows/
│       └── summarize.yml        # Cron schedule (every 15 min)
│
├── src/
│   ├── main.py                  # Entry point - orchestrates everything
│   ├── youtube.py               # YouTube API (OAuth for read + write)
│   ├── transcript.py            # Get video transcripts
│   ├── summarizer.py            # Claude Haiku summarization
│   └── notion_client.py         # Save to Notion + track processed
│
├── scripts/
│   └── get_refresh_token.py     # One-time OAuth setup script
│
├── PLAN.md                      # This file
├── SECURITY.md                  # Security instructions
├── requirements.txt             # Python dependencies
├── .gitignore                   # Prevent secret leaks
├── .env.example                 # Template for environment variables
└── README.md                    # Setup instructions
```

## Notion Database Schema

```
┌────────────────────────────────────────────────────────────────────────┐
│  📚 Video Summaries                                              Notion │
├──────────────┬──────────────┬─────────────────────────────────────────┤
│ Property     │ Type         │ Description                             │
├──────────────┼──────────────┼─────────────────────────────────────────┤
│ Title        │ Title        │ Video title                             │
│ Video ID     │ Text         │ YouTube video ID (for deduplication)    │
│ URL          │ URL          │ Link to video                           │
│ Channel      │ Text         │ Channel name                            │
│ Summary      │ Text         │ AI-generated summary                    │
│ Key Points   │ Text         │ Bullet points of main takeaways         │
│ Duration     │ Text         │ Video length                            │
│ Added        │ Date         │ When processed                          │
│ Status       │ Select       │ Pending / Summarized / Error            │
└──────────────┴──────────────┴─────────────────────────────────────────┘
```

## OAuth Flow (One-Time Setup)

Moving videos between playlists requires OAuth 2.0 (not just an API key).

```
┌─────────────────────────────────────────────────────────────────┐
│  INITIAL SETUP (once)                                           │
│                                                                 │
│  1. Run: python scripts/get_refresh_token.py                    │
│           │                                                     │
│           ▼                                                     │
│  2. Browser opens → Google login → "Allow access?"              │
│           │                                                     │
│           ▼                                                     │
│  3. Script receives authorization code                          │
│           │                                                     │
│           ▼                                                     │
│  4. Exchanges for refresh_token (long-lived)                    │
│           │                                                     │
│           ▼                                                     │
│  5. Store refresh_token in GitHub Secrets                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  AUTOMATED RUNS (ongoing)                                       │
│                                                                 │
│  GitHub Action uses refresh_token → Gets fresh access_token     │
│  → Makes API calls → Works indefinitely                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## GitHub Actions Workflow

```yaml
# .github/workflows/summarize.yml

name: Summarize Videos

on:
  schedule:
    - cron: '*/15 * * * *'    # Every 15 minutes
  workflow_dispatch:           # Manual trigger for testing

jobs:
  summarize:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python src/main.py
        env:
          YOUTUBE_CLIENT_ID: ${{ secrets.YOUTUBE_CLIENT_ID }}
          YOUTUBE_CLIENT_SECRET: ${{ secrets.YOUTUBE_CLIENT_SECRET }}
          YOUTUBE_REFRESH_TOKEN: ${{ secrets.YOUTUBE_REFRESH_TOKEN }}
          YOUTUBE_INPUT_PLAYLIST: ${{ secrets.YOUTUBE_INPUT_PLAYLIST }}
          YOUTUBE_OUTPUT_PLAYLIST: ${{ secrets.YOUTUBE_OUTPUT_PLAYLIST }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
          NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}
```

## Summarization Prompt

```
SYSTEM: You summarize YouTube video transcripts concisely.

USER: Summarize this video transcript.

      Title: {title}
      Channel: {channel}
      Transcript: {transcript}

      Provide:
      1. A 2-3 sentence summary
      2. 3-5 key takeaways as bullet points
      3. Who would find this video useful
```

## Required Secrets (GitHub Settings → Secrets)

| Secret | Description | Where to Get |
|--------|-------------|--------------|
| `YOUTUBE_CLIENT_ID` | OAuth client ID | Google Cloud Console |
| `YOUTUBE_CLIENT_SECRET` | OAuth client secret | Google Cloud Console |
| `YOUTUBE_REFRESH_TOKEN` | Long-lived auth token | Run `scripts/get_refresh_token.py` |
| `YOUTUBE_INPUT_PLAYLIST` | "📥 To Summarize" playlist ID | YouTube URL |
| `YOUTUBE_OUTPUT_PLAYLIST` | "✅ Summarized" playlist ID | YouTube URL |
| `ANTHROPIC_API_KEY` | Claude API key | console.anthropic.com |
| `NOTION_API_KEY` | Notion integration token | notion.so/my-integrations |
| `NOTION_DATABASE_ID` | Target database ID | Notion database URL |

## Setup Steps

```
1. Create YouTube playlists
   - "📥 To Summarize" (input)
   - "✅ Summarized" (output)
         │
         ▼
2. Google Cloud Console
   - Create project
   - Enable YouTube Data API v3
   - Create OAuth 2.0 credentials (Desktop app)
   - Download client_secret.json
         │
         ▼
3. Run OAuth setup locally
   - python scripts/get_refresh_token.py
   - Authorize in browser
   - Copy the refresh token
         │
         ▼
4. Notion setup
   - Create database with schema above
   - Create integration at notion.so/my-integrations
   - Share database with integration
         │
         ▼
5. GitHub setup
   - Create repository
   - Add all secrets (Settings → Secrets → Actions)
   - Push code
   - Enable Actions
         │
         ▼
6. Test
   - Trigger workflow manually (Actions → Run workflow)
   - Add a video to "📥 To Summarize"
   - Wait for next run (or trigger manually)
   - Check Notion for summary
         │
         ▼
7. Done! ✅
```

## Cost Estimate

| Component | Cost | Notes |
|-----------|------|-------|
| YouTube Data API | $0.00 | Free tier (10,000 units/day) |
| GitHub Actions | $0.00 | Free for public repos |
| Notion | $0.00 | Free tier |
| Claude Haiku | ~$0.002/video | ~$0.10-0.20/month for typical use |
| **Total** | **~$0.10-0.20/month** | Essentially free |

## Error Handling

- **No transcript available**: Save to Notion with "No transcript" note, still move to output playlist
- **API rate limits**: Implement exponential backoff
- **OAuth token expired**: Refresh token should auto-renew; if fails, re-run setup script
- **Notion API errors**: Log and retry on next run
