# Security Guidelines

This repository is public. Follow these guidelines to keep your credentials safe.

## ⚠️ Golden Rule: Never Commit Secrets

All sensitive values must be stored in **GitHub Secrets** only.

```
✅ GitHub Secrets (encrypted, secure)
❌ Hardcoded in code
❌ In .env files committed to repo
❌ In comments or documentation
```

## Protected Files

The following are in `.gitignore` and must **NEVER** be committed:

```
.env                    # Environment variables
*.json                  # Credential files (client_secret.json, etc.)
token.json              # Cached OAuth tokens
__pycache__/            # Python cache
*.pyc                   # Compiled Python
```

## Required Secrets

Store these in GitHub Settings → Secrets and variables → Actions:

| Secret | Description | How to Get |
|--------|-------------|------------|
| `YOUTUBE_CLIENT_ID` | OAuth 2.0 client ID | Google Cloud Console → APIs & Services → Credentials |
| `YOUTUBE_CLIENT_SECRET` | OAuth 2.0 client secret | Same as above |
| `YOUTUBE_REFRESH_TOKEN` | Long-lived auth token | Run `scripts/get_refresh_token.py` locally |
| `YOUTUBE_INPUT_PLAYLIST` | Playlist ID for input | From YouTube playlist URL |
| `YOUTUBE_OUTPUT_PLAYLIST` | Playlist ID for output | From YouTube playlist URL |
| `ANTHROPIC_API_KEY` | Claude API key | console.anthropic.com |
| `NOTION_API_KEY` | Notion integration token | notion.so/my-integrations |
| `NOTION_DATABASE_ID` | Database ID | From Notion database URL |

## Getting Playlist IDs

From a YouTube playlist URL:
```
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxx
                                      └─────────────────┘
                                       This is the playlist ID
```

## Getting Notion Database ID

From a Notion database URL:
```
https://www.notion.so/workspace/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...
                                └────────────────────────────────┘
                                 This is the database ID (remove hyphens)
```

## Local Development

When developing locally:

1. **Create `.env` file** (never commit this):
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

2. **Verify `.gitignore`** includes `.env`:
   ```bash
   grep ".env" .gitignore
   ```

3. **Check before committing**:
   ```bash
   git status  # Make sure .env is not listed
   ```

## If You Accidentally Commit a Secret

### Immediate Actions

1. **Revoke the exposed credential immediately**
   - YouTube: Google Cloud Console → Credentials → Delete and recreate
   - Anthropic: console.anthropic.com → API Keys → Revoke
   - Notion: notion.so/my-integrations → Revoke and recreate

2. **Remove from Git history** using BFG Repo-Cleaner or git filter-branch

3. **Force push** (coordinate with any collaborators):
   ```bash
   git push origin --force --all
   ```

4. **Regenerate all credentials** that were in the exposed file

### GitHub Secret Scanning

GitHub automatically scans for known secret patterns. If detected:
- You'll receive an alert
- The credential provider may be notified
- Act immediately to revoke and rotate

## Workflow Security

### DO ✅

```yaml
# Pass secrets as environment variables
- run: python src/main.py
  env:
    API_KEY: ${{ secrets.API_KEY }}
```

### DON'T ❌

```yaml
# Never echo or print secrets
- run: echo ${{ secrets.API_KEY }}

# Never use secrets in URLs or commands directly
- run: curl "https://api.example.com?key=${{ secrets.API_KEY }}"
```

## Credential Rotation Schedule

Recommended rotation frequency:

| Credential | Rotation | Notes |
|------------|----------|-------|
| YouTube OAuth | When revoked | Refresh tokens are long-lived |
| Anthropic API Key | Every 90 days | Or if suspected compromise |
| Notion API Key | Every 90 days | Or if suspected compromise |

## Scopes and Permissions

### YouTube OAuth Scopes

Only request necessary scopes:
```
https://www.googleapis.com/auth/youtube.readonly   # Read playlists
https://www.googleapis.com/auth/youtube            # Modify playlists
```

### Notion Integration

- Only share the specific database needed with the integration
- Don't grant workspace-wide access

## Audit Checklist

Before making the repo public, verify:

- [ ] `.env` is in `.gitignore`
- [ ] No secrets in any `.py` files
- [ ] No secrets in `PLAN.md` or `README.md`
- [ ] No `client_secret.json` or similar files
- [ ] Git history is clean (no previous secret commits)
- [ ] All actual values are in GitHub Secrets
- [ ] `.env.example` only contains placeholder values

## Reporting Security Issues

If you discover a security vulnerability in this project:
1. Do not open a public issue
2. Contact the repository owner directly
3. Allow reasonable time for a fix before disclosure
