# YouTube Video Summarizer

Automatically summarize YouTube videos and save them to Notion. Add a video to your "To Summarize" playlist, and the automation handles the rest.

## How It Works

```
You: See interesting video → Add to "📥 To Summarize" playlist → Done!

Automation (every 15 min via GitHub Actions):
  1. Checks playlist for new videos
  2. Fetches transcript via Supadata API
  3. Summarizes with Claude Haiku (~$0.002/video)
  4. Saves summary to Notion database
  5. Sends Slack notification (optional)
  6. Moves video to "✅ Summarized" playlist
```

## Features

- **Fully automated** - GitHub Actions runs every 15 minutes
- **Smart deduplication** - Tracks processed videos in Notion to avoid re-processing
- **Error handling** - Videos without transcripts are logged gracefully
- **Slack notifications** - Get notified when new summaries are ready (optional)
- **Cheap to run** - ~$0.10-0.30/month for typical usage

## Setup

### 1. Create YouTube Playlists

Create two playlists on YouTube:
- **📥 To Summarize** - Videos you want summarized
- **✅ Summarized** - Processed videos (auto-populated)

Note the playlist IDs from their URLs:
```
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx
                                      └─── This is the ID
```

### 2. Google Cloud Setup (YouTube API)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable **YouTube Data API v3**:
   - APIs & Services → Library → Search "YouTube Data API v3" → Enable
4. Create OAuth credentials:
   - APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Desktop app**
   - Download the JSON file as `client_secret.json`

### 3. Get YouTube Refresh Token

Run the OAuth setup script locally:

```bash
# Install dependencies
pip install google-auth-oauthlib

# Run setup (with client_secret.json in current directory)
python scripts/get_refresh_token.py
```

This opens a browser for authorization. After approving, copy the refresh token.

### 4. Notion Setup

1. Create a database with these properties:

   | Property | Type | Description |
   |----------|------|-------------|
   | Title | Title | Video title |
   | Video ID | Text | YouTube video ID |
   | URL | URL | Link to video |
   | Channel | Text | Channel name |
   | Summary | Text | AI-generated summary |
   | Key Points | Text | Bullet points |
   | Duration | Text | Video length |
   | Added | Date | When processed |
   | Status | Select | Pending/Summarized/Error |

2. Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
3. Share your database with the integration (click "..." → "Add connections")
4. Note the database ID from the URL:
   ```
   https://notion.so/workspace/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...
                              └─── Database ID (32 chars, remove hyphens)
   ```

### 5. Get Supadata API Key (Transcript Service)

This project uses [Supadata](https://supadata.ai) to fetch YouTube transcripts reliably (bypasses IP restrictions that affect direct YouTube access from GitHub Actions).

1. Sign up at [supadata.ai](https://supadata.ai)
2. Create an API key from the dashboard
3. Note: Uses ~1 credit per video transcript (native captions only, no AI generation)

### 6. Get Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Create an API key
3. Add some credits (usage is ~$0.002 per video with Claude Haiku)

### 7. Slack Notifications (Optional)

To receive Slack notifications when videos are summarized:

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app
2. Enable **Incoming Webhooks**
3. Add a webhook to your desired channel
4. Copy the webhook URL

### 8. GitHub Repository Setup

1. Fork or clone this repository
2. Go to Settings → Secrets and variables → Actions
3. Add these secrets:

   | Secret | Required | Description |
   |--------|----------|-------------|
   | `YOUTUBE_CLIENT_ID` | Yes | From Google Cloud OAuth credentials |
   | `YOUTUBE_CLIENT_SECRET` | Yes | From Google Cloud OAuth credentials |
   | `YOUTUBE_REFRESH_TOKEN` | Yes | From step 3 above |
   | `YOUTUBE_INPUT_PLAYLIST` | Yes | "To Summarize" playlist ID |
   | `YOUTUBE_OUTPUT_PLAYLIST` | Yes | "Summarized" playlist ID |
   | `SUPADATA_API_KEY` | Yes | From Supadata dashboard |
   | `ANTHROPIC_API_KEY` | Yes | From Anthropic console |
   | `NOTION_API_KEY` | Yes | From Notion integration |
   | `NOTION_DATABASE_ID` | Yes | From Notion database URL |
   | `SLACK_WEBHOOK_URL` | No | Slack incoming webhook URL |

4. Enable GitHub Actions (Actions tab → Enable workflows)

### 9. Test It

1. Add a video to your "📥 To Summarize" playlist
2. Go to Actions tab → "Summarize Videos" → "Run workflow"
3. Check your Notion database for the summary
4. Video should move to "✅ Summarized" playlist

## Local Development

```bash
# Clone the repo
git clone https://github.com/yourusername/youtube-summarizer
cd youtube-summarizer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your credentials

# Run
python src/main.py
```

## Cost Breakdown

| Service | Cost |
|---------|------|
| YouTube Data API | Free (10,000 quota units/day) |
| Supadata | ~$0.001/video (1 credit for native transcripts) |
| Claude Haiku | ~$0.002/video |
| Notion | Free |
| GitHub Actions | Free (public repos) / 2,000 min/month (private) |
| **Total** | **~$0.10-0.30/month** (for ~50-100 videos) |

## Troubleshooting

### "No transcript available"

Some videos don't have captions enabled. These are logged as "Error" entries in Notion and still moved to the output playlist to avoid reprocessing.

### "Quota exceeded"

YouTube API has daily limits (10,000 units). The automation processes videos incrementally, so it will catch up over subsequent runs.

### "OAuth token expired"

Refresh tokens are long-lived but can expire. Re-run `scripts/get_refresh_token.py` to get a new one, then update the `YOUTUBE_REFRESH_TOKEN` secret.

### "Supadata API error"

- **401**: Invalid API key - check `SUPADATA_API_KEY`
- **429**: Rate limit - wait and retry
- **404**: Video has no captions available

### Videos not moving to output playlist

Ensure your OAuth credentials have the `youtube` scope (not just `youtube.readonly`). Re-run the OAuth setup if needed.

## Project Structure

```
youtube-summarizer/
├── .github/workflows/
│   └── summarize.yml      # GitHub Actions workflow (runs every 15 min)
├── src/
│   ├── main.py            # Entry point & orchestration
│   ├── youtube.py         # YouTube API client (OAuth 2.0)
│   ├── transcript.py      # Supadata API client for transcripts
│   ├── summarizer.py      # Claude Haiku integration
│   ├── notion_db.py       # Notion API client
│   └── slack_notify.py    # Slack notifications
├── scripts/
│   └── get_refresh_token.py  # One-time OAuth setup helper
├── .env.example           # Environment variable template
├── requirements.txt       # Python dependencies
└── README.md
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  YouTube API    │────▶│  Supadata API    │────▶│  Claude Haiku   │
│  (video list)   │     │  (transcripts)   │     │  (summaries)    │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                        ┌─────────────────────────────────┘
                        ▼
              ┌──────────────────┐     ┌─────────────────┐
              │  Notion API      │     │  Slack Webhook  │
              │  (storage)       │     │  (notifications)│
              └──────────────────┘     └─────────────────┘
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT
