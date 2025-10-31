// Members JavaScript

let allMembers = [];

// Load members
function loadMembers() {
    const gid = localStorage.getItem('selectedGuildId');
    const url = gid ? `/api/members?guild_id=${gid}` : '/api/members';
    fetch(url)
        .then(response => response.json())
        .then(data => {
            allMembers = data;
            displayMembers(data);
        })
        .catch(error => {
            console.error('Error loading members:', error);
            document.getElementById('members-list').innerHTML = 
                '<tr><td colspan="5" class="loading">Failed to load members</td></tr>';
        });
}

// Display members in table
function displayMembers(members) {
    const tbody = document.getElementById('members-list');
    
    if (members.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading">No members found</td></tr>';
        return;
    }
    
    tbody.innerHTML = members.map(member => `
        <tr>
            <td><img src="${member.avatar}" alt="${member.name}"></td>
            <td>${member.name}#${member.discriminator}</td>
            <td>${member.id}</td>
            <td>${member.joined_at}</td>
            <td>${member.roles.join(', ') || 'No roles'}</td>
        </tr>
    `).join('');
}

// Search members
function searchMembers() {
    const searchTerm = document.getElementById('search-members').value.toLowerCase();
    
    if (searchTerm === '') {
        displayMembers(allMembers);
        return;
    }
    
    const filtered = allMembers.filter(member => 
        member.name.toLowerCase().includes(searchTerm) ||
        member.id.includes(searchTerm) ||
        member.roles.some(role => role.toLowerCase().includes(searchTerm))
    );
    
    displayMembers(filtered);
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    loadMembers();
});