from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import discord
import asyncio
import threading
from datetime import datetime
import json
import os
from functools import wraps
import traceback

app = Flask(__name__)
app.secret_key = 'super-secret-key-change-this-12345'

# Bot instance
bot = None
bot_stats = {
    'total_members': 0,
    'verified_members': 0,
    'pending_members': 0,
    'total_servers': 0,
    'uptime_start': datetime.utcnow(),
    'recent_logs': []
}

# Bot config references
bot_config = {
    'VERIFICATION_ROLE_ID': None,
    'PENDING_ROLE_ID': None,
    'QUARANTINE_ROLE_ID': None,
    'verified_users': set(),
    'WHITELISTED_BOTS': set(),
    'bot_actions': {},
    'user_violations': {}
}

# Helpers to run async code from Flask thread
def run_on_loop(coro, timeout=10):
    future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    return future.result(timeout=timeout)

def get_guild_by_id(guild_id: int):
    if not bot:
        return None
    for g in bot.guilds:
        if g.id == guild_id:
            return g
    return None

def any_text_channel(guild):
    return guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'hkmkmn1631'

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Error handler
@app.errorhandler(Exception)
def handle_error(e):
    print(f"ERROR: {e}")
    print(traceback.format_exc())
    return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

# ==================== ROUTES ====================
@app.route('/')
@login_required
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Error loading index: {e}<br><pre>{traceback.format_exc()}</pre>"

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                session['logged_in'] = True
                session.permanent = True
                return redirect(url_for('index'))
            return render_template('login.html', error='Invalid credentials')
        return render_template('login.html')
    except Exception as e:
        return f"Error in login: {e}"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/send_message')
@login_required
def send_message_page():
    try:
        return render_template('send_message.html')
    except Exception as e:
        return f"Error loading send_message: {e}<br>Make sure templates/send_message.html exists!"

@app.route('/bot_management')
@login_required
def bot_management_page():
    try:
        return render_template('bot_management.html')
    except Exception as e:
        return f"Error loading bot_management: {e}"

@app.route('/violations')
@login_required
def violations_page():
    try:
        return render_template('violations.html')
    except Exception as e:
        return f"Error loading violations: {e}"

@app.route('/config_page')
@login_required
def config_page():
    try:
        return render_template('config.html')
    except Exception as e:
        return f"Error loading config: {e}"

@app.route('/members')
@login_required
def members_page():
    try:
        return render_template('members.html')
    except Exception as e:
        return f"Error loading members: {e}"

@app.route('/logs')
@login_required
def logs_page():
    try:
        return render_template('logs.html')
    except Exception as e:
        return f"Error loading logs: {e}"

# ==================== API ROUTES ====================
@app.route('/api/stats')
@login_required
def get_stats():
    try:
        if bot and bot.guilds:
            guild_id_param = request.args.get('guild_id')
            if guild_id_param:
                guild = get_guild_by_id(int(guild_id_param)) or (bot.guilds[0] if bot.guilds else None)
                total_members = guild.member_count if guild else 0
            else:
                total_members = sum(g.member_count for g in bot.guilds)
            verified = len(bot_config['verified_users'])
            pending = 0
            return jsonify({
                'total_members': total_members,
                'verified_members': verified,
                'pending_members': pending,
                'total_servers': len(bot.guilds),
                'uptime': str(datetime.utcnow() - bot_stats['uptime_start']).split('.')[0],
                'bot_status': 'Online' if bot.is_ready() else 'Offline',
                'bot_name': str(bot.user) if bot.user else 'Bot'
            })
    except Exception as e:
        print(f"Stats error: {e}")
    
    return jsonify({
        'total_members': 0,
        'verified_members': 0,
        'pending_members': 0,
        'total_servers': 0,
        'uptime': '0:00:00',
        'bot_status': 'Offline',
        'bot_name': 'Not Connected'
    })

@app.route('/api/channels')
@login_required
def get_channels():
    try:
        if bot and bot.guilds:
            guild_id_param = request.args.get('guild_id')
            guild = get_guild_by_id(int(guild_id_param)) if guild_id_param else (bot.guilds[0] if bot.guilds else None)
            if not guild:
                return jsonify([])
            channels = []
            for channel in guild.text_channels:
                channels.append({
                    'id': str(channel.id),
                    'name': channel.name,
                    'category': channel.category.name if channel.category else 'No Category'
                })
            return jsonify(channels)
    except Exception as e:
        print(f"Channels error: {e}")
    return jsonify([])

@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    try:
        data = request.json
        message = data.get('message')
        broadcast = bool(data.get('broadcast'))
        channel_id = data.get('channel_id')
        channel_name = data.get('channel_name')
        
        if not bot or not bot.is_ready():
            return jsonify({'success': False, 'message': 'Bot is not connected to Discord'})
        
        if broadcast:
            async def send_all():
                sent = 0
                for g in list(bot.guilds):
                    ch = None
                    if channel_name:
                        ch = discord.utils.get(g.text_channels, name=channel_name)
                    if not ch:
                        ch = any_text_channel(g)
                    if ch:
                        try:
                            await ch.send(message)
                            sent += 1
                        except Exception:
                            pass
                return sent
            sent_count = run_on_loop(send_all())
            return jsonify({'success': True, 'message': f'Broadcast sent to {sent_count} server(s).'})
        else:
            if not channel_id:
                return jsonify({'success': False, 'message': 'channel_id required when not broadcasting'})
            channel = bot.get_channel(int(channel_id))
            if not channel:
                return jsonify({'success': False, 'message': 'Channel not found'})
            async def send():
                await channel.send(message)
            run_on_loop(send())
            return jsonify({'success': True, 'message': 'Message sent successfully!'})
    except Exception as e:
        print(f"Send message error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/send_embed', methods=['POST'])
@login_required
def send_embed():
    try:
        data = request.json
        channel_id = data.get('channel_id')
        broadcast = bool(data.get('broadcast'))
        channel_name = data.get('channel_name')
        title = data.get('title')
        description = data.get('description')
        color = data.get('color', '#5865F2')
        
        if not bot or not bot.is_ready():
            return jsonify({'success': False, 'message': 'Bot is not connected'})
        
        if broadcast:
            async def send_all():
                color_int = int(color.replace('#', ''), 16)
                sent = 0
                for g in list(bot.guilds):
                    ch = None
                    if channel_name:
                        ch = discord.utils.get(g.text_channels, name=channel_name)
                    if not ch:
                        ch = any_text_channel(g)
                    if ch:
                        try:
                            embed = discord.Embed(title=title, description=description, color=color_int)
                            embed.set_footer(text="Sent via Dashboard")
                            await ch.send(embed=embed)
                            sent += 1
                        except Exception:
                            pass
                return sent
            sent_count = run_on_loop(send_all())
            return jsonify({'success': True, 'message': f'Broadcast embed sent to {sent_count} server(s).'})
        else:
            if not channel_id:
                return jsonify({'success': False, 'message': 'channel_id required when not broadcasting'})
            channel = bot.get_channel(int(channel_id))
            if not channel:
                return jsonify({'success': False, 'message': 'Channel not found'})
            async def send():
                color_int = int(color.replace('#', ''), 16)
                embed = discord.Embed(title=title, description=description, color=color_int)
                embed.set_footer(text="Sent via Dashboard")
                await channel.send(embed=embed)
            run_on_loop(send())
            return jsonify({'success': True, 'message': 'Embed sent successfully!'})
    except Exception as e:
        print(f"Send embed error: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/members')
@login_required  
def get_members():
    try:
        if bot and bot.guilds:
            guild_id_param = request.args.get('guild_id')
            guild = get_guild_by_id(int(guild_id_param)) if guild_id_param else (bot.guilds[0] if bot.guilds else None)
            if not guild:
                return jsonify([])
            members = []
            for member in list(guild.members)[:100]:
                members.append({
                    'id': str(member.id),
                    'name': member.name,
                    'discriminator': member.discriminator,
                    'avatar': str(member.display_avatar.url),
                    'joined_at': member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown',
                    'roles': [r.name for r in member.roles if r.name != '@everyone'],
                    'is_bot': member.bot
                })
            return jsonify(members)
    except Exception as e:
        print(f"Members error: {e}")
    return jsonify([])

@app.route('/api/bots')
@login_required
def get_bots():
    try:
        if bot and bot.guilds:
            guild_id_param = request.args.get('guild_id')
            guild = get_guild_by_id(int(guild_id_param)) if guild_id_param else (bot.guilds[0] if bot.guilds else None)
            if not guild:
                return jsonify([])
            bots = []
            for member in guild.members:
                if member.bot:
                    bots.append({
                        'id': str(member.id),
                        'name': member.name,
                        'avatar': str(member.display_avatar.url),
                        'whitelisted': member.id in bot_config['WHITELISTED_BOTS'],
                        'action_count': len(bot_config['bot_actions'].get(member.id, [])),
                        'joined_at': member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown'
                    })
            return jsonify(bots)
    except Exception as e:
        print(f"Bots error: {e}")
    return jsonify([])

@app.route('/api/violations')
@login_required
def get_violations():
    try:
        if bot and bot.guilds:
            guild_id_param = request.args.get('guild_id')
            guild = get_guild_by_id(int(guild_id_param)) if guild_id_param else (bot.guilds[0] if bot.guilds else None)
            if not guild:
                return jsonify([])
            violations = []
            for user_id, count in bot_config['user_violations'].items():
                member = guild.get_member(user_id)
                if member:
                    violations.append({
                        'id': str(member.id),
                        'name': member.name,
                        'avatar': str(member.display_avatar.url),
                        'violations': count
                    })
            return jsonify(sorted(violations, key=lambda x: x['violations'], reverse=True))
    except Exception as e:
        print(f"Violations error: {e}")
    return jsonify([])

@app.route('/api/config', methods=['GET', 'POST'])
@login_required
def config():
    try:
        config_file = 'bot_config.json'
        
        if request.method == 'POST':
            data = request.json
            with open(config_file, 'w') as f:
                json.dump(data, f, indent=2)
            return jsonify({'success': True, 'message': 'Configuration updated'})
        
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return jsonify(json.load(f))
        else:
            return jsonify({
                'raid_threshold': 5,
                'raid_window': 60,
                'spam_threshold': 5,
                'mass_ping_threshold': 5,
                'bad_words': ['potangina', 'tangina'],
                'use_math_captcha': False,
                'custom_dm_message': 'Welcome!',
                'custom_welcome_message': 'Welcome {user}!',
                'lockdown_default_minutes': 10
            })
    except Exception as e:
        print(f"Config error: {e}")
        return jsonify({'error': str(e)})

@app.route('/api/logs')
@login_required
def get_logs():
    return jsonify({'logs': bot_stats.get('recent_logs', [])})

# =============== NEW: Guilds list ===============
@app.route('/api/guilds')
@login_required
def get_guilds():
    try:
        if not bot:
            return jsonify([])
        data = []
        for g in bot.guilds:
            data.append({
                'id': str(g.id),
                'name': g.name,
                'member_count': g.member_count
            })
        return jsonify(data)
    except Exception as e:
        print(f"Guilds error: {e}")
        return jsonify([])

# =============== Anti-nuke controls ===============
@app.route('/api/raidmode', methods=['POST'])
@login_required
def api_raidmode():
    try:
        data = request.json
        action = (data.get('action') or '').lower()
        guild_id = data.get('guild_id')
        target_guilds = [get_guild_by_id(int(guild_id))] if guild_id else list(bot.guilds)
        if action not in ['on', 'off']:
            return jsonify({'success': False, 'message': 'Action must be on/off'})
        import bot as bot_module
        async def toggle(g):
            if action == 'on':
                await bot_module.trigger_raid_mode(g, await bot_module.get_log_channel(g))
            else:
                await bot_module.deactivate_raid_mode(g, await bot_module.get_log_channel(g))
        for g in target_guilds:
            if g:
                run_on_loop(toggle(g))
        return jsonify({'success': True, 'message': f'Raid mode {action} executed.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/lockdown', methods=['POST'])
@login_required
def api_lockdown():
    try:
        data = request.json
        minutes = int(data.get('minutes', 10))
        guild_id = data.get('guild_id')
        target_guilds = [get_guild_by_id(int(guild_id))] if guild_id else list(bot.guilds)
        async def do_lock(g):
            import bot as bot_module
            log_channel = await bot_module.get_log_channel(g)
            # lock
            for ch in g.text_channels:
                try:
                    overwrite = ch.overwrites_for(g.default_role)
                    overwrite.send_messages = False
                    await ch.set_permissions(g.default_role, overwrite=overwrite, reason='Dashboard lockdown')
                except Exception:
                    pass
            if log_channel:
                await log_channel.send(embed=bot_module.create_log_embed('🔒 Lockdown Activated', f'Dashboard lockdown for {minutes} minutes.'))
            if minutes > 0:
                await asyncio.sleep(minutes * 60)
                for ch in g.text_channels:
                    try:
                        overwrite = ch.overwrites_for(g.default_role)
                        overwrite.send_messages = None
                        await ch.set_permissions(g.default_role, overwrite=overwrite, reason='Dashboard lockdown end')
                    except Exception:
                        pass
                if log_channel:
                    await log_channel.send(embed=bot_module.create_log_embed('Lockdown Deactivated', 'Server unlocked.', discord.Color.green()))
        for g in target_guilds:
            if g:
                asyncio.run_coroutine_threadsafe(do_lock(g), bot.loop)
        return jsonify({'success': True, 'message': 'Lockdown initiated.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/backup', methods=['POST'])
@login_required
def api_backup():
    try:
        guild_id = request.json.get('guild_id')
        target_guilds = [get_guild_by_id(int(guild_id))] if guild_id else list(bot.guilds)
        import bot as bot_module
        for g in target_guilds:
            if g:
                run_on_loop(bot_module.snapshot_guild(g))
        return jsonify({'success': True, 'message': 'Backup completed.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/restore', methods=['POST'])
@login_required
def api_restore():
    try:
        guild_id = request.json.get('guild_id')
        target_guilds = [get_guild_by_id(int(guild_id))] if guild_id else list(bot.guilds)
        import bot as bot_module
        restored_any = False
        for g in target_guilds:
            if g and run_on_loop(bot_module.restore_from_snapshot(g)):
                restored_any = True
        return jsonify({'success': restored_any, 'message': 'Restore attempted.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/approve_bot', methods=['POST'])
@login_required
def api_approve_bot():
    try:
        data = request.json
        guild_id = int(data.get('guild_id'))
        bot_id = int(data.get('bot_id'))
        try:
            import secun0c as bot_module
        except Exception:
            import bot as bot_module
        guild = get_guild_by_id(guild_id)
        if not guild:
            return jsonify({'success': False, 'message': 'Guild not found'})
        member = guild.get_member(bot_id)
        if not member or not member.bot:
            return jsonify({'success': False, 'message': 'Bot not found in guild'})
        bot_module.WHITELISTED_BOTS.add(bot_id)
        async def apply():
            q_role = await bot_module.get_quarantine_role(guild)
            if q_role and q_role in member.roles:
                await member.remove_roles(q_role, reason='Dashboard approve bot')
            log_channel = await bot_module.get_log_channel(guild)
            if log_channel:
                await log_channel.send(embed=bot_module.create_log_embed('🤖 Bot Approved', f'{member.mention} approved via dashboard.', discord.Color.green()))
        run_on_loop(apply())
        return jsonify({'success': True, 'message': 'Bot approved.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/revoke_bot', methods=['POST'])
@login_required
def api_revoke_bot():
    try:
        data = request.json
        guild_id = int(data.get('guild_id'))
        bot_id = int(data.get('bot_id'))
        try:
            import secun0c as bot_module
        except Exception:
            import bot as bot_module
        guild = get_guild_by_id(guild_id)
        if not guild:
            return jsonify({'success': False, 'message': 'Guild not found'})
        member = guild.get_member(bot_id)
        if not member or not member.bot:
            return jsonify({'success': False, 'message': 'Bot not found in guild'})
        if bot_id in bot_module.WHITELISTED_BOTS:
            bot_module.WHITELISTED_BOTS.discard(bot_id)
        async def apply():
            q_role = await bot_module.get_quarantine_role(guild)
            if q_role:
                await member.add_roles(q_role, reason='Dashboard revoke bot')
            log_channel = await bot_module.get_log_channel(guild)
            if log_channel:
                await log_channel.send(embed=bot_module.create_log_embed('🤖 Bot Revoked', f'{member.mention} quarantined via dashboard.', discord.Color.orange()))
        run_on_loop(apply())
        return jsonify({'success': True, 'message': 'Bot revoked.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/kick_bot', methods=['POST'])
@login_required
def api_kick_bot():
    try:
        data = request.json
        guild_id = int(data.get('guild_id'))
        bot_id = int(data.get('bot_id'))
        try:
            import secun0c as bot_module
        except Exception:
            import bot as bot_module
        guild = get_guild_by_id(guild_id)
        if not guild:
            return jsonify({'success': False, 'message': 'Guild not found'})
        member = guild.get_member(bot_id)
        if not member or not member.bot:
            return jsonify({'success': False, 'message': 'Bot not found in guild'})
        async def do_kick():
            await member.kick(reason='Dashboard kick bot')
            log_channel = await bot_module.get_log_channel(guild)
            if log_channel:
                await log_channel.send(embed=bot_module.create_log_embed('🤖 Bot Kicked', f'{member.name} kicked via dashboard.', discord.Color.red()))
        run_on_loop(do_kick())
        return jsonify({'success': True, 'message': 'Bot kicked.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)

def start_dashboard(discord_bot):
    global bot
    bot = discord_bot
    
    # Import bot variables
    try:
        try:
            import secun0c as bot_module
        except Exception:
            import bot as bot_module
        bot_config['VERIFICATION_ROLE_ID'] = bot_module.VERIFICATION_ROLE_ID
        bot_config['PENDING_ROLE_ID'] = bot_module.PENDING_ROLE_ID
        bot_config['QUARANTINE_ROLE_ID'] = bot_module.QUARANTINE_ROLE_ID
        bot_config['verified_users'] = bot_module.verified_users
        bot_config['WHITELISTED_BOTS'] = bot_module.WHITELISTED_BOTS
        bot_config['bot_actions'] = bot_module.bot_actions
        bot_config['user_violations'] = bot_module.user_violations
        print("✅ Bot config loaded successfully")
    except Exception as e:
        print(f"⚠️  Bot config warning: {e}")
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ Dashboard started on http://localhost:5000")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=55000, debug=True)