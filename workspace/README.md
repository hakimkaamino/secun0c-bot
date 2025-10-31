# 🛡️ SECUN0C - Ultimate Anti-Nuke Security Bot

Complete Discord server protection against nukers, raiders, and malicious attacks.

## 🚀 Features

- **Immediate Ban System** - No warnings, instant bans on detection
- **Auto-Restore** - Automatic recovery from nukes using backups
- **Smart Role Hierarchy Detection** - Prevents role elevation attacks
- **Channel/Role Spam Detection** - Detects both creation and deletion spam
- **Enhanced Bot Detection** - Auto-quarantine + ban dangerous bots
- **Webhook Guard** - 24/7 webhook deletion and blocking
- **Rate Limit Aware** - Handles Discord API rate limits gracefully
- **Real-Time Logging** - Web dashboard for monitoring
- **Guild Owner Protection** - Never bans server owner

## 📋 Requirements

- Python 3.10 or 3.11
- Discord Bot Token
- Bot with Administrator permissions (recommended)

## 🏗️ Setup

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` file with your bot token:
   ```
   DISCORD_TOKEN=your_token_here
   ```
4. Run the bot: `python secun0c.py`
5. In your Discord server, run `!setup`
6. Access dashboard at `http://localhost:5000` (default login: admin/hkmkmn1631)

## 📝 Commands

- `!xfeatures` - View all bot features
- `!setup` - Setup security roles & channels
- `!backup` - Create server snapshot
- `!restore` - Restore from backup
- `!raidmode on/off` - Toggle raid protection
- `!lockdown [mins]` - Emergency lockdown

## 🔐 Security

Change the dashboard password in `dashboard.py` before deploying!

## 📄 License

Private - For personal use only

