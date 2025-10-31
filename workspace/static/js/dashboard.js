// Dashboard JavaScript

// Update stats every 5 seconds
function updateStats() {
    const gid = localStorage.getItem('selectedGuildId');
    const url = gid ? `/api/stats?guild_id=${gid}` : '/api/stats';
    fetch(url)
        .then(response => response.json())
        .then(data => {
            document.getElementById('total-members').textContent = data.total_members;
            document.getElementById('verified-members').textContent = data.verified_members;
            document.getElementById('pending-members').textContent = data.pending_members;
            document.getElementById('total-servers').textContent = data.total_servers;
            document.getElementById('uptime').textContent = data.uptime;
            document.getElementById('status-text').textContent = data.bot_status;
            document.getElementById('last-updated').textContent = 'Just now';
            
            // Update status badge
            const statusBadge = document.getElementById('bot-status');
            if (data.bot_status === 'Online') {
                statusBadge.className = 'status-badge online';
            } else {
                statusBadge.className = 'status-badge offline';
            }
        })
        .catch(error => {
            console.error('Error fetching stats:', error);
        });
}

// Toggle Raid Mode
function toggleRaidMode(action) {
    const gid = localStorage.getItem('selectedGuildId');
    fetch('/api/raidmode', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ action: action, guild_id: gid })
    })
    .then(response => response.json())
    .then(data => {
        alert(data.message);
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Failed to toggle raid mode');
    });
}

// Show Lockdown Modal
function showLockdownModal() {
    document.getElementById('lockdownModal').style.display = 'block';
}

// Close Lockdown Modal
function closeLockdownModal() {
    document.getElementById('lockdownModal').style.display = 'none';
}

// Trigger Lockdown
function triggerLockdown() {
    const minutes = document.getElementById('lockdown-minutes').value;
    const gid = localStorage.getItem('selectedGuildId');
    fetch('/api/lockdown', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ minutes: parseInt(minutes), guild_id: gid })
    })
    .then(response => response.json())
    .then(data => {
        alert(data.message);
        closeLockdownModal();
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Failed to activate lockdown');
    });
}

// Backup and Restore
function doBackup() {
    const gid = localStorage.getItem('selectedGuildId');
    fetch('/api/backup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: gid })
    })
    .then(r => r.json())
    .then(d => alert(d.message || 'Backup done'))
    .catch(() => alert('Backup failed'));
}

function doRestore() {
    const gid = localStorage.getItem('selectedGuildId');
    fetch('/api/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ guild_id: gid })
    })
    .then(r => r.json())
    .then(d => alert(d.message || 'Restore attempted'))
    .catch(() => alert('Restore failed'));
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('lockdownModal');
    if (event.target == modal) {
        closeLockdownModal();
    }
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', function() {
    updateStats();
    setInterval(updateStats, 5000); // Update every 5 seconds
    // Populate guild selector if present
    const sel = document.getElementById('guild-select');
    if (sel) {
        fetch('/api/guilds')
            .then(r => r.json())
            .then(gs => {
                const saved = localStorage.getItem('selectedGuildId');
                sel.innerHTML = '<option value="">All Servers</option>';
                gs.forEach(g => {
                    const opt = document.createElement('option');
                    opt.value = g.id;
                    opt.textContent = `${g.name} (${g.member_count})`;
                    if (saved && saved === g.id) opt.selected = true;
                    sel.appendChild(opt);
                });
                sel.addEventListener('change', () => {
                    const val = sel.value || '';
                    if (val) localStorage.setItem('selectedGuildId', val); else localStorage.removeItem('selectedGuildId');
                    updateStats();
                });
            })
            .catch(() => {});
    }
});