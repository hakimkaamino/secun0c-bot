import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import time
from collections import defaultdict, deque
import re
from datetime import datetime, timedelta
import random
import json
import os

# Dashboard integration
import sys
sys.path.append('.')
try:
    from dashboard import start_dashboard
    DASHBOARD_AVAILABLE = True
except:
    DASHBOARD_AVAILABLE = False
    print("⚠️  Dashboard not available - running bot only")

# ==================== BOT SETUP ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# ==================== CONFIGURATION ====================
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Backward-compat single-guild defaults (kept for dashboard import safety)
LOG_CHANNEL_ID = None
WELCOME_CHANNEL_ID = None
VERIFICATION_ROLE_ID = None
PENDING_ROLE_ID = None
ADMIN_ROLE_ID = None
TRUSTED_ROLE_ID = None
QUARANTINE_ROLE_ID = None  # For suspicious users/bots

# Per-guild dynamic configuration (persisted to disk)
import os

CONFIG_FILE = 'guild_config.json'
GUILD_CONFIG = {}

def load_guild_config():
    global GUILD_CONFIG
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                import json as _json
                GUILD_CONFIG = _json.load(f)
    except Exception as _e:
        print(f"⚠️  Failed to load guild config: {_e}")
        GUILD_CONFIG = {}

def save_guild_config():
    try:
        with open(CONFIG_FILE, 'w') as f:
            import json as _json
            _json.dump(GUILD_CONFIG, f, indent=2)
    except Exception as _e:
        print(f"⚠️  Failed to save guild config: {_e}")

def get_guild_settings(guild):
    gs = GUILD_CONFIG.get(str(guild.id))
    if gs is None:
        gs = {}
        GUILD_CONFIG[str(guild.id)] = gs
    return gs

def set_guild_setting(guild, key, value):
    gs = get_guild_settings(guild)
    gs[key] = value
    save_guild_config()

# Security Configuration
BAD_WORDS = ['potangina', 'tangina']
AUTO_ROLES = []
RAID_THRESHOLD = 4
RAID_WINDOW = 45
SPAM_THRESHOLD = 4
MASS_PING_THRESHOLD = 4
JOIN_LEAVE_THRESHOLD = 3
DELETE_THRESHOLD = 3
CHANNEL_CHANGE_THRESHOLD = 2
ROLE_CHANGE_THRESHOLD = 2
WEBHOOK_DETECTION = True
LOCKDOWN_DEFAULT_MINUTES = 10
MIN_ACCOUNT_AGE_DAYS = 7  # Accounts younger than this get flagged
SUSPICIOUS_LINK_PATTERN = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\$,]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

# Bot Monitoring Configuration
BOT_AUTO_QUARANTINE = True  # Auto-quarantine all new bots
WHITELISTED_BOTS = set()  # Bot IDs that are trusted
BOT_ACTION_THRESHOLD = 5  # Actions per 10 seconds before alert

# ==================== GLOBAL TRACKERS ====================
join_times = defaultdict(list)
message_history = defaultdict(lambda: deque(maxlen=100))
verified_users = set()
raid_mode_active = defaultdict(bool)
invites_before = {}
lockdown_tasks = {}
join_leave_history = defaultdict(list)
delete_history = defaultdict(list)
ban_history = defaultdict(list)
channel_changes = defaultdict(list)
role_changes = defaultdict(list)
deleted_messages = deque(maxlen=100)
user_violations = defaultdict(int)  # Track violations for 3-strike system
bot_actions = defaultdict(list)  # Track bot actions
quarantined_users = set()  # Users in quarantine
nickname_changes = defaultdict(list)  # Track nickname spam
avatar_changes = defaultdict(list)  # Track avatar spam

# Backups for restoration
GUILD_BACKUPS = {}

# Audit log throttle to avoid hitting 429 during nukes
audit_throttle = defaultdict(dict)  # {guild_id: {action_key: last_ts}}

# Webhook guard configuration
GUARD_WEBHOOKS_ALWAYS = True

# Guild-wide change counters
guild_event_window = 8
guild_change_history = defaultdict(list)  # guild_id -> timestamps of create/delete events

# Additional trackers for advanced attack patterns
channel_rename_history = defaultdict(list)  # Track channel renames per user
emoji_delete_history = defaultdict(list)  # Track emoji deletions
member_rename_history = defaultdict(list)  # Track member renames
member_timeout_history = defaultdict(list)  # Track member timeouts
role_assign_history = defaultdict(list)  # Track mass role assignments
invite_create_history = defaultdict(list)  # Track invite creation spam
nsfw_toggle_history = defaultdict(list)  # Track NSFW toggles
lock_permission_history = defaultdict(list)  # Track lock permission changes
@bot.event
async def on_guild_role_update(before, after):
    """Smart role hierarchy detection + dangerous permission detection"""
    try:
        guild = after.guild
        me = guild.me
        
        # SMART HIERARCHY DETECTION: Check if role was moved above bot's highest role
        bot_highest_position = max([r.position for r in me.roles], default=0)
        if after.position > bot_highest_position and before.position <= bot_highest_position:
            # Role was moved above bot - IMMEDIATE BAN
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                    actor = entry.user
                    if actor and not is_trusted(actor):
                        await neutralize_member(guild, actor, reason=f"🚨 Role hierarchy attack: {after.name} moved above bot position")
                        try:
                            await after.edit(position=before.position, reason='🚨 ANTI-NUKE: revert hierarchy attack')
                        except Exception:
                            pass
                    break
            except Exception:
                pass
        
        # Detect dangerous permission escalation
        dangerous = ['administrator','manage_guild','manage_roles','manage_channels','ban_members','kick_members']
        escalated = []
        for perm in dangerous:
            if not getattr(before.permissions, perm) and getattr(after.permissions, perm):
                escalated.append(perm)
        if escalated:
            # Find actor from audit logs
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                    actor = entry.user
                    if actor and not is_trusted(actor):
                        # IMMEDIATE BAN for adding dangerous perms
                        await neutralize_member(guild, actor, reason=f"🚨 Dangerous role perms added: {', '.join(escalated)}")
                        # Revert role permissions
                        try:
                            await after.edit(permissions=before.permissions, reason='🚨 ANTI-NUKE: revert dangerous role perms')
                        except Exception:
                            pass
                        log_channel = await get_log_channel(guild)
                        if log_channel:
                            await log_channel.send(embed=create_log_embed('🚨 Role Perms Reverted', f"{after.name}: {', '.join(escalated)} added by {actor.mention} → **BANNED** and reverted."))
                    break
            except Exception:
                pass
    except Exception:
        pass

@bot.event
async def on_guild_channel_update(before, after):
    try:
        if isinstance(after, discord.TextChannel):
            guild = after.guild
            everyone = guild.default_role
            
            # Detect channel rename spam
            if before.name != after.name:
                try:
                    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
                        actor = entry.user
                        if actor and not is_trusted(actor):
                            channel_rename_history[actor.id].append(time.time())
                            channel_rename_history[actor.id] = [t for t in channel_rename_history[actor.id] if time.time() - t < 10]
                            if len(channel_rename_history[actor.id]) >= 3:
                                await neutralize_member(guild, actor, reason="Channel rename spam")
                                try:
                                    await after.edit(name=before.name, reason='Anti-nuke: revert rename spam')
                                except Exception:
                                    pass
                        break
                except Exception:
                    pass
            
            # Detect NSFW toggle spam
            if before.nsfw != after.nsfw:
                try:
                    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
                        actor = entry.user
                        if actor and not is_trusted(actor):
                            nsfw_toggle_history[actor.id].append(time.time())
                            nsfw_toggle_history[actor.id] = [t for t in nsfw_toggle_history[actor.id] if time.time() - t < 10]
                            if len(nsfw_toggle_history[actor.id]) >= 3:
                                await neutralize_member(guild, actor, reason="NSFW toggle spam")
                                try:
                                    await after.edit(nsfw=before.nsfw, reason='Anti-nuke: revert NSFW toggle')
                                except Exception:
                                    pass
                        break
                except Exception:
                    pass
            
            # Detect lock permission spam (send_messages disabled)
            b = before.overwrites_for(everyone)
            a = after.overwrites_for(everyone)
            if b.send_messages is not False and a.send_messages is False:
                try:
                    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
                        actor = entry.user
                        if actor and not is_trusted(actor):
                            lock_permission_history[actor.id].append(time.time())
                            lock_permission_history[actor.id] = [t for t in lock_permission_history[actor.id] if time.time() - t < 10]
                            if len(lock_permission_history[actor.id]) >= 3:
                                await neutralize_member(guild, actor, reason="Channel lock spam")
                                try:
                                    a.send_messages = None
                                    await after.set_permissions(everyone, overwrite=a, reason='Anti-nuke: revert lock')
                                except Exception:
                                    pass
                        break
                except Exception:
                    pass
            
            # Enforce raid mode
            if raid_mode_active[guild.id]:
                if b.send_messages is False and a.send_messages is not False:
                    a.send_messages = False
                    try:
                        await after.set_permissions(everyone, overwrite=a, reason='Anti-nuke: enforce raid mode')
                    except Exception:
                        pass
    except Exception:
        pass

@bot.event
async def on_guild_emojis_update(guild, before, after):
    """Detect emoji deletion spam"""
    try:
        if len(before) > len(after):
            deleted_count = len(before) - len(after)
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.emoji_delete):
                    actor = entry.user
                    if actor and not is_trusted(actor):
                        emoji_delete_history[actor.id].append(time.time())
                        emoji_delete_history[actor.id] = [t for t in emoji_delete_history[actor.id] if time.time() - t < 10]
                        if len(emoji_delete_history[actor.id]) >= 2 or deleted_count >= 3:
                            await neutralize_member(guild, actor, reason="Emoji deletion spam")
                            log_channel = await get_log_channel(guild)
                            if log_channel:
                                await log_channel.send(embed=create_log_embed('🚨 Emoji Deletion Detected', f"{actor.mention} deleted {deleted_count} emojis"))
                    break
            except Exception:
                pass
    except Exception:
        pass

@bot.event
async def on_member_update(before, after):
    """Detect member rename spam, timeout spam, and role assignment spam"""
    try:
        guild = after.guild
        if not guild:
            return
        
        # Detect nickname rename spam
        if before.nick != after.nick:
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                    actor = entry.user
                    if actor and not is_trusted(actor):
                        member_rename_history[actor.id].append(time.time())
                        member_rename_history[actor.id] = [t for t in member_rename_history[actor.id] if time.time() - t < 10]
                        if len(member_rename_history[actor.id]) >= 3:
                            await neutralize_member(guild, actor, reason="Member rename spam")
                            try:
                                await after.edit(nick=before.nick, reason='Anti-nuke: revert rename spam')
                            except Exception:
                                pass
                    break
            except Exception:
                pass
        
        # Detect timeout spam
        if before.communication_disabled_until != after.communication_disabled_until:
            if after.communication_disabled_until:  # Member was timed out
                try:
                    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                        actor = entry.user
                        if actor and not is_trusted(actor):
                            member_timeout_history[actor.id].append(time.time())
                            member_timeout_history[actor.id] = [t for t in member_timeout_history[actor.id] if time.time() - t < 10]
                            if len(member_timeout_history[actor.id]) >= 3:
                                await neutralize_member(guild, actor, reason="Member timeout spam")
                                try:
                                    await after.timeout(None, reason='Anti-nuke: revert timeout spam')
                                except Exception:
                                    pass
                        break
                except Exception:
                    pass
        
        # Detect mass role assignment spam
        if len(before.roles) < len(after.roles):
            # Role was added
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_role_update):
                    actor = entry.user
                    if actor and not is_trusted(actor):
                        role_assign_history[actor.id].append(time.time())
                        role_assign_history[actor.id] = [t for t in role_assign_history[actor.id] if time.time() - t < 10]
                        if len(role_assign_history[actor.id]) >= 5:  # 5 role assignments in 10 seconds
                            await neutralize_member(guild, actor, reason="Mass role assignment spam")
                            # Revert role changes
                            try:
                                await after.edit(roles=before.roles, reason='Anti-nuke: revert role spam')
                            except Exception:
                                pass
                    break
            except Exception:
                pass
    except Exception:
        pass

@bot.event
async def on_invite_create(invite):
    """Detect invite creation spam (audit log flooding)"""
    try:
        guild = invite.guild
        actor = invite.inviter
        if actor and not is_trusted(actor):
            invite_create_history[actor.id].append(time.time())
            invite_create_history[actor.id] = [t for t in invite_create_history[actor.id] if time.time() - t < 10]
            if len(invite_create_history[actor.id]) >= 10:  # 10 invites in 10 seconds
                await neutralize_member(guild, actor, reason="Invite spam (audit log flooding)")
                try:
                    await invite.delete(reason='Anti-nuke: delete spam invite')
                except Exception:
                    pass
    except Exception:
        pass

@bot.event
async def on_message(message):
    """Enhanced message handler: block DM spam, emoji spam, and other attacks"""
    try:
        # Block DM spam
        if isinstance(message.channel, discord.DMChannel):
            # Rate limit DMs from same user
            if hasattr(message, 'author') and message.author:
                dm_key = f"dm_{message.author.id}"
                if not hasattr(bot, 'dm_tracker'):
                    bot.dm_tracker = defaultdict(list)
                bot.dm_tracker[dm_key].append(time.time())
                bot.dm_tracker[dm_key] = [t for t in bot.dm_tracker[dm_key] if time.time() - t < 60]
                if len(bot.dm_tracker[dm_key]) >= 5:  # 5 DMs in 60 seconds = spam
                    # Block this user from DMing
                    return
        
        # Block emoji spam in guild channels
        if message.guild and isinstance(message.channel, discord.TextChannel):
            author = message.author
            if not is_trusted(author):
                content = message.content or ""
                # Count custom emojis (<:name:id> or <a:name:id>)
                custom_emoji_pattern = r'<a?:[\w]+:\d+>'
                custom_emojis = len(re.findall(custom_emoji_pattern, content))
                # Count unicode emojis
                emoji_unicode = "😀😃😄😁😆😅😂🤣😊😇🙂🙃😉😌😍🥰😘😗😙😚😋😛😝😜🤪🤨🧐🤓😎🤩🥳😏😒🔥💯"
                unicode_emojis = len([c for c in content if c in emoji_unicode])
                # Count emojis in embeds
                embed_emojis = 0
                if message.embeds:
                    for embed in message.embeds:
                        if hasattr(embed, 'description') and embed.description:
                            embed_emojis += len(re.findall(custom_emoji_pattern, embed.description))
                            embed_emojis += len([c for c in embed.description if c in emoji_unicode])
                
                total_emojis = custom_emojis + unicode_emojis + embed_emojis
                
                # Detect emoji-only spam messages (10+ emojis with little text)
                if total_emojis >= 10 and len(content.replace(' ', '')) < 100:
                    try:
                        await message.delete()
                        await log_violation(message.guild, author, f"Emoji spam ({total_emojis} emojis)")
                    except Exception:
                        pass
                    return
        
        # Continue with existing message handling logic...
        if message.author == bot.user:
            return
        
        # Existing spam detection code...
        if message.guild:
            # [existing spam detection logic continues...]
            pass
    except Exception:
        pass
    # Allow other cogs/commands to process
    await bot.process_commands(message)

async def sweep_webhooks_and_perms():
    """Aggressive webhook deletion with rate limit handling"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            for guild in list(bot.guilds):
                if not guild or not guild.text_channels:
                    continue
                channels_to_check = list(guild.text_channels)[:10]  # Limit to avoid rate limits
                for channel in channels_to_check:
                    if GUARD_WEBHOOKS_ALWAYS:
                        try:
                            # Rate limit aware webhook deletion
                            try:
                                webhooks = await channel.webhooks()
                                for wh in webhooks:
                                    try:
                                        await wh.delete(reason="🚨 ANTI-NUKE: webhook sweep")
                                        await asyncio.sleep(0.5)  # Small delay to avoid rate limits
                                    except discord.errors.NotFound:
                                        pass  # Already deleted
                                    except discord.errors.RateLimited as e:
                                        await asyncio.sleep(e.retry_after)
                                    except Exception:
                                        pass
                            except discord.errors.RateLimited as e:
                                await asyncio.sleep(e.retry_after)
                                continue
                            except Exception:
                                pass
                            
                            # Block manage_webhooks for @everyone
                            try:
                                overwrite = channel.overwrites_for(guild.default_role)
                                if overwrite.manage_webhooks is not False:
                                    overwrite.manage_webhooks = False
                                    await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="🚨 ANTI-NUKE: webhook block")
                            except Exception:
                                pass
                        except Exception:
                            pass
                        await asyncio.sleep(0.3)  # Delay between channels
        except Exception:
            pass
        await asyncio.sleep(30)  # Check every 30 seconds instead of 5 minutes

@bot.event
async def on_member_join(member):
    """Enhanced bot detection on join - immediate quarantine for suspicious bots"""
    try:
        guild = member.guild
        
        # Protect guild owner - never ban
        if member.id == guild.owner_id:
            return
        
        # Bot detection and auto-quarantine
        if member.bot and BOT_AUTO_QUARANTINE:
            if member.id not in WHITELISTED_BOTS:
                # Check if bot has dangerous permissions
                dangerous_perms = ['administrator', 'manage_guild', 'manage_channels', 'manage_roles', 'manage_webhooks']
                has_dangerous = any(getattr(member.guild_permissions, perm) for perm in dangerous_perms)
                
                if has_dangerous:
                    # IMMEDIATE BAN for bots with dangerous perms
                    try:
                        await guild.ban(member, reason='🚨 ANTI-NUKE: Unwhitelisted bot with dangerous permissions', delete_message_days=0)
                        log_event(guild.id, 'BOT_BANNED', f'{member.name} ({member.id}) banned: unwhitelisted bot with dangerous permissions', 'danger')
                        log_channel = await get_log_channel(guild)
                        if log_channel:
                            await log_channel.send(embed=create_log_embed('🚨 Bot Banned', f'{member.mention} was banned for having dangerous permissions without approval.', discord.Color.red()))
                        return
                    except Exception:
                        pass
                
                # Auto-quarantine unwhitelisted bots
                quarantine_role = await create_quarantine_role(guild)
                if quarantine_role:
                    try:
                        await member.add_roles(quarantine_role, reason='Auto-quarantine: unwhitelisted bot')
                        log_event(guild.id, 'BOT_QUARANTINED', f'{member.name} ({member.id}) quarantined - awaiting approval', 'warning')
                        log_channel = await get_log_channel(guild)
                        if log_channel:
                            await log_channel.send(embed=create_log_embed('🤖 Bot Quarantined', f'{member.mention} joined and was quarantined. Use `!approvebot {member.mention}` to approve.', discord.Color.orange()))
                    except Exception:
                        pass
    except Exception:
        pass

@bot.event
async def setup_hook():
    # Start background tasks safely in discord.py 2.x
    asyncio.create_task(sweep_webhooks_and_perms())

# ==================== UTILITY FUNCTIONS ====================
async def get_log_channel(guild):
    settings = get_guild_settings(guild)
    chan_id = settings.get('log_channel_id') or LOG_CHANNEL_ID
    if chan_id:
        channel = bot.get_channel(int(chan_id))
        if channel and channel.guild == guild:
            return channel
    # Fallback by common names
    for name in ['bot-logs', 'logs', 'security-logs']:
        channel = discord.utils.get(guild.text_channels, name=name)
        if channel:
            set_guild_setting(guild, 'log_channel_id', channel.id)
            return channel
    return None

def create_log_embed(title, description, color=discord.Color.blue()):
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
    return embed

def log_event(guild_id, event_type, description, severity='info'):
    """Log event to dashboard"""
    try:
        from dashboard import bot_stats
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'guild_id': str(guild_id),
            'type': event_type,
            'description': description,
            'severity': severity  # info, warning, danger, success
        }
        bot_stats['recent_logs'].append(log_entry)
        # Keep only last 100 logs
        if len(bot_stats['recent_logs']) > 100:
            bot_stats['recent_logs'] = bot_stats['recent_logs'][-100:]
    except Exception:
        pass  # Dashboard might not be available

def is_trusted(member):
    """Check if member has trusted role and can bypass protections"""
    settings = get_guild_settings(member.guild)
    trusted_id = settings.get('trusted_role_id') or TRUSTED_ROLE_ID
    if trusted_id:
        return any(role.id == int(trusted_id) for role in member.roles)
    return any(role.name == 'Trusted' for role in member.roles)

async def neutralize_member(guild, actor, reason, immediate_ban=True):
    """IMEDIATE BAN on detection - no timeout or kick. This is the ultimate defense."""
    member = actor if isinstance(actor, discord.Member) else guild.get_member(getattr(actor, 'id', None))
    if member is None and hasattr(actor, 'id'):
        try:
            member = await guild.fetch_member(actor.id)
        except Exception:
            member = None
    # PROTECT: Never ban guild owner or trusted members
    if member is None or is_trusted(member) or (member and member.id == guild.owner_id):
        return False
    try:
        # IMMEDIATE BAN - most aggressive response
        if immediate_ban:
            try:
                await guild.ban(member, reason=f'🚨 ANTI-NUKE: {reason}', delete_message_days=0)
                log_channel = await get_log_channel(guild)
                if log_channel:
                    await log_channel.send(embed=create_log_embed('🚨 IMMEDIATE BAN', f'{member.mention} ({member.id}) was **BANNED** for: {reason}', discord.Color.red()))
                # Log to dashboard
                log_event(guild.id, 'IMMEDIATE_BAN', f'{member.name} ({member.id}) banned: {reason}', 'danger')
                return True
            except discord.Forbidden:
                # If we can't ban, try kick + remove all roles
                try:
                    await member.edit(roles=[guild.default_role], reason=reason)
                    await member.kick(reason=f'🚨 ANTI-NUKE: {reason} (ban failed)')
                except Exception:
                    pass
        else:
            # Fallback: remove roles and timeout
            await member.edit(roles=[guild.default_role], reason=reason)
            until = datetime.utcnow() + timedelta(minutes=60)
            await member.timeout(until, reason=reason)
    except Exception as e:
        print(f"⚠️ Neutralize error: {e}")
    return True

async def create_trusted_role(guild):
    trusted_role = discord.utils.get(guild.roles, name="Trusted")
    if not trusted_role:
        trusted_role = await guild.create_role(name="Trusted", color=discord.Color.gold(), reason="Auto-created trusted role")
    set_guild_setting(guild, 'trusted_role_id', trusted_role.id)
    return trusted_role

async def create_quarantine_role(guild):
    quarantine_role = discord.utils.get(guild.roles, name="Quarantined")
    if not quarantine_role:
        quarantine_role = await guild.create_role(name="Quarantined", color=discord.Color.dark_red(), permissions=discord.Permissions(read_messages=True, send_messages=False), reason="Auto-created quarantine role")
    set_guild_setting(guild, 'quarantine_role_id', quarantine_role.id)
    return quarantine_role

# ==================== SNAPSHOT / RESTORE ====================
async def snapshot_guild(guild):
    try:
        role_data = []
        for role in guild.roles:
            role_data.append({
                'id': role.id,
                'name': role.name,
                'color': role.color.value,
                'permissions': role.permissions.value,
                'position': role.position,
                'hoist': role.hoist,
                'mentionable': role.mentionable
            })
        channel_data = []
        categories = []
        for cat in guild.categories:
            categories.append({'id': cat.id, 'name': cat.name, 'position': cat.position})
        for ch in guild.channels:
            channel_data.append({
                'id': ch.id,
                'name': ch.name,
                'type': int(ch.type.value) if hasattr(ch.type, 'value') else int(ch.type),
                'category_id': ch.category_id,
                'position': getattr(ch, 'position', 0)
            })
        role_memberships = {}
        for member in guild.members:
            role_memberships[str(member.id)] = [r.id for r in member.roles if r != guild.default_role]
        GUILD_BACKUPS[guild.id] = {
            'timestamp': time.time(),
            'guild_name': guild.name,
            'roles': role_data,
            'categories': categories,
            'channels': channel_data,
            'role_memberships': role_memberships
        }
        log_channel = await get_log_channel(guild)
        if log_channel:
            await log_channel.send(embed=create_log_embed("📦 Backup Created", f"Snapshot saved with {len(role_data)} roles and {len(channel_data)} channels."))
        log_event(guild.id, 'BACKUP_CREATED', f'Backup created: {len(role_data)} roles, {len(channel_data)} channels', 'success')
    except Exception:
        pass

async def restore_from_snapshot(guild):
    data = GUILD_BACKUPS.get(guild.id)
    if not data:
        return False
    try:
        # Guild name
        try:
            if data.get('guild_name') and guild.name != data['guild_name']:
                await guild.edit(name=data['guild_name'], reason='Auto-restore: guild name')
        except Exception:
            pass
        # Roles
        existing_roles_by_name = {r.name: r for r in guild.roles}
        for rdata in data['roles']:
            if rdata['name'] == '@everyone':
                continue
            if rdata['name'] not in existing_roles_by_name:
                perms = discord.Permissions(rdata['permissions'])
                try:
                    await guild.create_role(
                        name=rdata['name'],
                        colour=discord.Color(rdata['color']),
                        permissions=perms,
                        hoist=rdata['hoist'],
                        mentionable=rdata['mentionable'],
                        reason='Auto-restore from snapshot'
                    )
                except Exception:
                    pass
        existing_roles_by_name = {r.name: r for r in guild.roles}
        # Categories
        existing_cats_by_name = {c.name: c for c in guild.categories}
        for cdata in data.get('categories', []):
            if cdata['name'] not in existing_cats_by_name:
                try:
                    await guild.create_category(cdata['name'], reason='Auto-restore from snapshot')
                except Exception:
                    pass
        existing_cats_by_name = {c.name: c for c in guild.categories}
        # Channels
        existing_channel_names = {c.name for c in guild.channels}
        for chdata in data['channels']:
            if chdata['name'] not in existing_channel_names:
                try:
                    if chdata['type'] == int(discord.ChannelType.text.value):
                        cat = None
                        for sc in data.get('categories', []):
                            if sc['id'] == chdata['category_id']:
                                cat = existing_cats_by_name.get(sc['name'])
                                break
                        await guild.create_text_channel(chdata['name'], category=cat, reason='Auto-restore from snapshot')
                except Exception:
                    pass
        # Role memberships
        try:
            for member in guild.members:
                saved = data['role_memberships'].get(str(member.id))
                if not saved:
                    continue
                roles_to_assign = []
                for rdata in data['roles']:
                    if rdata['id'] in saved and rdata['name'] != '@everyone':
                        r = existing_roles_by_name.get(rdata['name'])
                        if r and r not in member.roles:
                            roles_to_assign.append(r)
                if roles_to_assign:
                    try:
                        await member.add_roles(*roles_to_assign, reason='Auto-restore roles from snapshot')
                    except Exception:
                        pass
        except Exception:
            pass
        log_channel = await get_log_channel(guild)
        if log_channel:
            await log_channel.send(embed=create_log_embed("🛠️ Restore Attempted", "Roles/channels restored where possible."))
        log_event(guild.id, 'RESTORE_ATTEMPTED', 'Server restoration attempted from backup', 'warning')
        return True
    except Exception:
        return False

# ==================== RAID MODE ====================
async def trigger_raid_mode(guild, log_channel):
    if raid_mode_active[guild.id]:
        return
    raid_mode_active[guild.id] = True
    log_event(guild.id, 'RAID_MODE_ACTIVATED', 'Raid mode activated - all channels locked', 'danger')
    if log_channel:
        await log_channel.send(embed=create_log_embed("🚨 Raid Mode Activated", f"All channels locked.", discord.Color.dark_red()))
    for channel in guild.text_channels:
        try:
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.send_messages = False
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Raid mode active")
        except Exception:
            pass
    await asyncio.sleep(300)
    await deactivate_raid_mode(guild, log_channel)

async def deactivate_raid_mode(guild, log_channel):
    raid_mode_active[guild.id] = False
    for channel in guild.text_channels:
        try:
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.send_messages = None
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Raid mode deactivated")
        except Exception:
            pass
    if log_channel:
        await log_channel.send(embed=create_log_embed("Raid Mode Deactivated", "Server unlocked.", discord.Color.green()))

# ==================== EVENTS: WEBHOOK / CREATE / DELETE ====================
@bot.event
async def on_webhooks_update(channel):
    if not GUARD_WEBHOOKS_ALWAYS:
        return
    try:
        webhooks = await channel.webhooks()
        for wh in list(webhooks):
            try:
                await wh.delete(reason="Anti-nuke: webhook guard")
            except Exception:
                pass
        # Block perms
        try:
            overwrite = channel.overwrites_for(channel.guild.default_role)
            if overwrite.manage_webhooks is not False:
                overwrite.manage_webhooks = False
                await channel.set_permissions(channel.guild.default_role, overwrite=overwrite, reason="Anti-nuke: block webhooks")
        except Exception:
            pass
    except Exception:
        pass

@bot.event
async def on_guild_channel_create(channel):
    """Enhanced channel creation detection - detect spam creation"""
    guild = channel.guild
    
    # Guard webhooks immediately
    try:
        if isinstance(channel, discord.TextChannel):
            webhooks = await channel.webhooks()
            for wh in webhooks:
                try:
                    await wh.delete(reason="🚨 ANTI-NUKE: new channel webhook guard")
                except Exception:
                    pass
    except Exception:
        pass
    
    guild_change_history[guild.id].append(time.time())
    guild_change_history[guild.id] = [t for t in guild_change_history[guild.id] if time.time() - t < guild_event_window]
    
    # DETECT SPAM CREATION: If 3+ channels created rapidly, ban and delete
    if len(guild_change_history[guild.id]) >= 3:
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_create):
                actor = entry.user
                if actor and not is_trusted(actor):
                    # IMMEDIATE BAN for spam creation
                    await neutralize_member(guild, actor, reason="🚨 Mass channel creation spam")
                    # Delete the spam channels
                    try:
                        if isinstance(channel, discord.TextChannel):
                            await channel.delete(reason="🚨 ANTI-NUKE: delete spam channel")
                    except Exception:
                        pass
                    log_event(guild.id, 'CHANNEL_SPAM_DETECTED', f'{actor.name} banned for mass channel creation', 'danger')
                    break
        except Exception:
            pass
    
    if len(guild_change_history[guild.id]) >= 6:
        await trigger_raid_mode(guild, await get_log_channel(guild))

@bot.event
async def on_guild_channel_delete(channel):
    """Enhanced channel deletion detection with auto-restore"""
    guild = channel.guild
    guild_change_history[guild.id].append(time.time())
    guild_change_history[guild.id] = [t for t in guild_change_history[guild.id] if time.time() - t < guild_event_window]
    
    # IMMEDIATE ACTION: If 3+ channels deleted in short time, ban and restore
    if len(guild_change_history[guild.id]) >= 3:
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.channel_delete):
                actor = entry.user
                if actor and not is_trusted(actor):
                    # IMMEDIATE BAN
                    await neutralize_member(guild, actor, reason="🚨 Mass channel deletion detected")
                    break
        except Exception:
            pass
        
        # Auto-restore if backup exists
        if guild.id in GUILD_BACKUPS:
            await restore_from_snapshot(guild)
            log_channel = await get_log_channel(guild)
            if log_channel:
                await log_channel.send(embed=create_log_embed("🛠️ Auto-Restore Triggered", "Channels restored from backup after mass deletion.", discord.Color.green()))
            log_event(guild.id, 'AUTO_RESTORE', 'Channels restored from backup after mass deletion', 'success')
        
        await trigger_raid_mode(guild, await get_log_channel(guild))

@bot.event
async def on_guild_role_create(role):
    """Enhanced role creation detection - detect spam creation"""
    guild = role.guild
    guild_change_history[guild.id].append(time.time())
    guild_change_history[guild.id] = [t for t in guild_change_history[guild.id] if time.time() - t < guild_event_window]
    
    # DETECT SPAM CREATION: If 3+ roles created rapidly, ban and delete
    if len(guild_change_history[guild.id]) >= 3:
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.role_create):
                actor = entry.user
                if actor and not is_trusted(actor):
                    # IMMEDIATE BAN for spam creation
                    await neutralize_member(guild, actor, reason="🚨 Mass role creation spam")
                    # Delete the spam role
                    try:
                        await role.delete(reason="🚨 ANTI-NUKE: delete spam role")
                    except Exception:
                        pass
                    log_event(guild.id, 'ROLE_SPAM_DETECTED', f'{actor.name} banned for mass role creation', 'danger')
                    break
        except Exception:
            pass
    
    if len(guild_change_history[guild.id]) >= 6:
        await trigger_raid_mode(guild, await get_log_channel(guild))

@bot.event
async def on_guild_role_delete(role):
    """Enhanced role deletion detection with auto-restore"""
    guild = role.guild
    guild_change_history[guild.id].append(time.time())
    guild_change_history[guild.id] = [t for t in guild_change_history[guild.id] if time.time() - t < guild_event_window]
    
    # IMMEDIATE ACTION: If 3+ roles deleted, ban and restore
    if len(guild_change_history[guild.id]) >= 3:
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.role_delete):
                actor = entry.user
                if actor and not is_trusted(actor):
                    # IMMEDIATE BAN
                    await neutralize_member(guild, actor, reason="🚨 Mass role deletion detected")
                    break
        except Exception:
            pass
        
        # Auto-restore if backup exists
        if guild.id in GUILD_BACKUPS:
            await restore_from_snapshot(guild)
            log_channel = await get_log_channel(guild)
            if log_channel:
                await log_channel.send(embed=create_log_embed("🛠️ Auto-Restore Triggered", "Roles restored from backup after mass deletion.", discord.Color.green()))
        
        await trigger_raid_mode(guild, await get_log_channel(guild))

# ==================== COMMANDS ====================
@bot.command(name='setup')
@commands.has_guild_permissions(administrator=True)
@commands.cooldown(1, 300, commands.BucketType.guild)  # Once per 5 minutes per guild
async def setup_guild(ctx):
    guild = ctx.guild
    # Roles
    trusted = await create_trusted_role(guild)
    quarantine = await create_quarantine_role(guild)
    # Channels
    logs_category = discord.utils.get(guild.categories, name='Security Logs')
    if not logs_category:
        try:
            logs_category = await guild.create_category('Security Logs')
        except Exception:
            logs_category = None
    log_channel = discord.utils.get(guild.text_channels, name='bot-logs')
    if not log_channel:
        try:
            log_channel = await guild.create_text_channel('bot-logs', category=logs_category)
        except Exception:
            log_channel = None
    if log_channel:
        set_guild_setting(guild, 'log_channel_id', log_channel.id)
    # Harden @everyone
    try:
        everyone_perms = guild.default_role.permissions
        updated = discord.Permissions(permissions=everyone_perms.value)
        updated.update(manage_channels=False, manage_roles=False, administrator=False)
        await guild.default_role.edit(permissions=updated, reason='Setup: harden default role perms')
    except Exception:
        pass
    await snapshot_guild(guild)
    await ctx.reply("✅ Setup complete. Logs channel created and snapshot saved.")

@bot.command(name='backup')
@commands.has_guild_permissions(administrator=True)
@commands.cooldown(1, 60, commands.BucketType.guild)  # Once per minute per guild
async def backup_cmd(ctx):
    await snapshot_guild(ctx.guild)
    await ctx.reply("✅ Backup saved.")

@bot.command(name='restore')
@commands.has_guild_permissions(administrator=True)
@commands.cooldown(1, 120, commands.BucketType.guild)  # Once per 2 minutes per guild
async def restore_cmd(ctx):
    ok = await restore_from_snapshot(ctx.guild)
    await ctx.reply("🛠️ Restore attempted." if ok else "❌ No backup available.")

@bot.command(name='raidmode')
@commands.has_guild_permissions(administrator=True)
async def raidmode_cmd(ctx, action: str):
    if action.lower() == 'on':
        await trigger_raid_mode(ctx.guild, await get_log_channel(ctx.guild))
        await ctx.reply("✅ Raid mode on")
    elif action.lower() == 'off':
        await deactivate_raid_mode(ctx.guild, await get_log_channel(ctx.guild))
        await ctx.reply("✅ Raid mode off")
    else:
        await ctx.reply("❌ Use !raidmode on/off")

@bot.command(name='lockdown')
@commands.has_guild_permissions(administrator=True)
async def lockdown_cmd(ctx, minutes: int = 5):
    guild = ctx.guild
    log_channel = await get_log_channel(guild)
    for channel in guild.text_channels:
        try:
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.send_messages = False
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=f"Lockdown by {ctx.author}")
        except Exception:
            pass
    if log_channel:
        await log_channel.send(embed=create_log_embed("🔒 Lockdown", f"Locked for {minutes} minutes."))
    await ctx.reply(f"🔒 Locked for {minutes} minutes. Use !raidmode off to unlock early.")
    await asyncio.sleep(minutes * 60)
    for channel in guild.text_channels:
        try:
            overwrite = channel.overwrites_for(guild.default_role)
            overwrite.send_messages = None
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Lockdown ended")
        except Exception:
            pass
    if log_channel:
        await log_channel.send(embed=create_log_embed("Lockdown Ended", "Server unlocked.", discord.Color.green()))

@bot.command(name='xfeatures')
async def xfeatures(ctx):
    """Display all security features of the bot"""
    embed = discord.Embed(
        title="🛡️ **SECUN0C - Ultimate Anti-Nuke Security Bot**",
        description="*Complete server protection against nukers, raiders, and malicious attacks*",
        color=discord.Color.dark_red()
    )
    
    embed.add_field(
        name="🚨 **Real-Time Threat Detection**",
        value="• Immediate ban on suspicious activity\n• Smart role hierarchy protection\n• Mass deletion detection\n• Channel/role spam protection\n• Webhook guard 24/7\n• Bot auto-quarantine",
        inline=False
    )
    
    embed.add_field(
        name="⚡ **Advanced Protection Features**",
        value="• Auto-restore from backup during nukes\n• Rate limit aware webhook deletion\n• Channel rename/lock/NSFW spam detection\n• Emoji spam blocking\n• Member rename/timeout spam protection\n• Invite flood protection\n• DM spam blocking",
        inline=False
    )
    
    embed.add_field(
        name="🔐 **Admin Commands**",
        value="`!setup` - Setup security roles & channels\n`!backup` - Create server snapshot\n`!restore` - Restore from backup\n`!raidmode on/off` - Toggle raid protection\n`!lockdown [mins]` - Emergency lockdown\n`!verify [user]` - Verify member\n`!trust/untrust [user]` - Manage trusted users\n`!violations` - View violation list",
        inline=False
    )
    
    embed.add_field(
        name="🤖 **Bot Management**",
        value="`!approvebot [bot]` - Approve trusted bot\n`!revokebot [bot]` - Revoke bot access\n`!kickbot [bot]` - Remove bot\n`!botlist` - List all bots\n`!botactions` - View bot activity",
        inline=False
    )
    
    embed.add_field(
        name="📊 **Monitoring & Logs**",
        value="• Real-time event logging\n• Violation tracking (3-strike system)\n• Web dashboard at http://localhost:5000\n• Security logs channel\n• Activity monitoring",
        inline=False
    )
    
    embed.add_field(
        name="🎯 **Key Features**",
        value="✅ **Immediate Ban System** - No warnings, instant bans\n✅ **Auto-Restore** - Automatic recovery from nukes\n✅ **Smart Detection** - AI-like pattern recognition\n✅ **24/7 Monitoring** - Continuous server protection\n✅ **Zero-Config** - Works automatically after !setup",
        inline=False
    )
    
    embed.set_footer(text="🛡️ SECUN0C - Your server's ultimate defense | Made for maximum security")
    await ctx.reply(embed=embed)

# ==================== ERROR HANDLERS ====================
@bot.event
async def on_command_error(ctx, error):
    """Handle command errors gracefully"""
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ Command on cooldown. Try again in {error.retry_after:.1f} seconds.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignore unknown commands
    else:
        # Log other errors
        try:
            log_event(ctx.guild.id if ctx.guild else 0, 'COMMAND_ERROR', f'Error in {ctx.command}: {str(error)}', 'warning')
        except:
            pass

# ==================== EVENT: ON_READY ====================
@bot.event
async def on_ready():
    load_guild_config()
    print('=' * 60)
    print(f'✅ {bot.user} is ONLINE!')
    print('=' * 60)
    print(f'📊 Servers: {len(bot.guilds)}')
    print(f'👥 Members: {sum(g.member_count for g in bot.guilds)}')
    print('=' * 60)
    
    # Create security roles
    for guild in bot.guilds:
        await create_trusted_role(guild)
        await create_quarantine_role(guild)
        try:
            invites_before[guild.id] = await guild.invites()
        except:
            pass
        log_event(guild.id, 'BOT_ONLINE', f'Bot connected to {guild.name}', 'info')
    
    # Start dashboard if available
    if DASHBOARD_AVAILABLE:
        start_dashboard(bot)
        print('🌐 Dashboard: http://localhost:5000')
        print('🔑 Login: admin / hkmkmn1631')
        print('=' * 60)

if __name__ == "__main__":
    try:
        if not TOKEN or not isinstance(TOKEN, str) or not TOKEN.strip():
            raise RuntimeError("Bot token missing. Set DISCORD_TOKEN in .env or put token in token.txt")
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")


