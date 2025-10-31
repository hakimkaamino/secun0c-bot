// Logs JavaScript

let allLogs = [];

// Load logs
function loadLogs() {
    fetch('/api/logs')
        .then(response => response.json())
        .then(data => {
            allLogs = data.logs || [];
            displayLogs(allLogs);
        })
        .catch(error => {
            console.error('Error loading logs:', error);
            document.getElementById('logs-container').innerHTML = 
                '<div class="log-entry"><span class="log-time">Failed to load logs</span></div>';
        });
}

// Display logs
function displayLogs(logs) {
    const container = document.getElementById('logs-container');
    
    if (logs.length === 0) {
        container.innerHTML = '<div class="log-entry"><span class="log-time">No logs available. Logs will appear here as events occur.</span></div>';
        return;
    }
    
    container.innerHTML = logs.map(log => `
        <div class="log-entry">
            <span class="log-time">${log.timestamp || 'Unknown time'}</span>
            <span class="log-type ${log.type || 'info'}">${(log.type || 'info').toUpperCase()}</span>
            <span>${log.message || 'No message'}</span>
        </div>
    `).join('');
}

// Filter logs
function filterLogs() {
    const filter = document.getElementById('log-type-filter').value;
    
    if (filter === 'all') {
        displayLogs(allLogs);
        return;
    }
    
    const filtered = allLogs.filter(log => log.type === filter);
    displayLogs(filtered);
}

// Refresh logs
function refreshLogs() {
    loadLogs();
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    loadLogs();
    // Auto-refresh every 10 seconds
    setInterval(loadLogs, 10000);
});