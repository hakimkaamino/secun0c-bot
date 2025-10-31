// Configuration JavaScript

let currentConfig = {};

// Load configuration
function loadConfig() {
    fetch('/api/config')
        .then(response => response.json())
        .then(data => {
            currentConfig = data;
            
            // Populate form fields
            document.getElementById('raid-threshold').value = data.raid_threshold || 5;
            document.getElementById('raid-window').value = data.raid_window || 60;
            document.getElementById('spam-threshold').value = data.spam_threshold || 5;
            document.getElementById('mass-ping-threshold').value = data.mass_ping_threshold || 5;
            document.getElementById('use-math-captcha').checked = data.use_math_captcha || false;
            document.getElementById('custom-dm-message').value = data.custom_dm_message || '';
            document.getElementById('custom-welcome-message').value = data.custom_welcome_message || '';
            document.getElementById('bad-words').value = (data.bad_words || []).join(', ');
            document.getElementById('lockdown-default-minutes').value = data.lockdown_default_minutes || 10;
        })
        .catch(error => {
            console.error('Error loading config:', error);
            showNotification('Failed to load configuration', 'error');
        });
}

// Save configuration
function saveConfig() {
    const config = {
        raid_threshold: parseInt(document.getElementById('raid-threshold').value),
        raid_window: parseInt(document.getElementById('raid-window').value),
        spam_threshold: parseInt(document.getElementById('spam-threshold').value),
        mass_ping_threshold: parseInt(document.getElementById('mass-ping-threshold').value),
        use_math_captcha: document.getElementById('use-math-captcha').checked,
        custom_dm_message: document.getElementById('custom-dm-message').value,
        custom_welcome_message: document.getElementById('custom-welcome-message').value,
        bad_words: document.getElementById('bad-words').value.split(',').map(w => w.trim()).filter(w => w),
        lockdown_default_minutes: parseInt(document.getElementById('lockdown-default-minutes').value)
    };
    
    fetch('/api/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(config)
    })
    .then(response => response.json())
    .then(data => {
        showNotification('Configuration saved successfully!', 'success');
    })
    .catch(error => {
        console.error('Error saving config:', error);
        showNotification('Failed to save configuration', 'error');
    });
}

// Show notification
function showNotification(message, type) {
    const notification = document.getElementById('save-notification');
    notification.textContent = message;
    notification.className = `notification ${type}`;
    notification.style.display = 'block';
    
    setTimeout(() => {
        notification.style.display = 'none';
    }, 3000);
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    loadConfig();
});