# YouTube Video Summarizer

Automatically summarize YouTube videos and save them to Notion. Add a video to your "To Summarize" playlist, and the automation handles the rest.

## How It Works

```
You: See interesting video → Add to "📥 To Summarize" playlist → Done!

Automation (every 15 min):
  1. Checks playlist for new videos
  2. Fetches transcript
  3. Summarizes with Claude Haiku (~$0.002/video)
  4. Saves summary to Notion
  5. Moves video to "✅ Summarized" playlist
```

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

### 2. Google Cloud Setup

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
   | Summary | Text | AI summary |
   | Key Points | Text | Bullet points |
   | Duration | Text | Video length |
   | Added | Date | When processed |
   | Status | Select | Pending/Summarized/Error |

2. Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
3. Share your database with the integration (click "..." → "Add connections")
4. Note the database ID from the URL:
   ```
   https://notion.so/workspace/xxxxxxxxxxxxxxxx?v=...
                              └─── Database ID (32 chars)
   ```

### 5. Get Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Create an API key
3. Add some credits (usage is ~$0.002 per video)

### 6. GitHub Repository Setup

1. Fork or clone this repository
2. Go to Settings → Secrets and variables → Actions
3. Add these secrets:

   | Secret | Value |
   |--------|-------|
   | `YOUTUBE_CLIENT_ID` | From Google Cloud OAuth credentials |
   | `YOUTUBE_CLIENT_SECRET` | From Google Cloud OAuth credentials |
   | `YOUTUBE_REFRESH_TOKEN` | From step 3 above |
   | `YOUTUBE_INPUT_PLAYLIST` | "To Summarize" playlist ID |
   | `YOUTUBE_OUTPUT_PLAYLIST` | "Summarized" playlist ID |
   | `ANTHROPIC_API_KEY` | From Anthropic console |
   | `NOTION_API_KEY` | From Notion integration |
   | `NOTION_DATABASE_ID` | From Notion database URL |

4. Enable GitHub Actions (Actions tab → Enable workflows)

### 7. Test It

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

## Cost

| Service | Cost |
|---------|------|
| YouTube Data API | Free (10k units/day) |
| GitHub Actions | Free (public repos) |
| Notion | Free |
| Claude Haiku | ~$0.002/video |
| **Total** | **~$0.10-0.20/month** |

## Troubleshooting

### "No transcript available"

Some videos don't have captions. These are logged as errors in Notion but still moved to the output playlist.

### "Quota exceeded"

YouTube API has daily limits. The automation processes videos incrementally, so it will catch up over time.

### "OAuth token expired"

Refresh tokens are long-lived but can expire. Re-run `scripts/get_refresh_token.py` to get a new one.

### Videos not moving

Check that your OAuth credentials have the `youtube` scope (not just `youtube.readonly`).

## Project Structure

```
youtube-summarizer/
├── .github/workflows/
│   └── summarize.yml      # GitHub Actions (runs every 15 min)
├── src/
│   ├── main.py            # Entry point
│   ├── youtube.py         # YouTube API client
│   ├── transcript.py      # Transcript fetcher
│   ├── summarizer.py      # Claude Haiku integration
│   └── notion_client.py   # Notion API client
├── scripts/
│   └── get_refresh_token.py  # OAuth setup helper
├── requirements.txt
└── README.md
```

## License

MIT
