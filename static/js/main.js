// Main JavaScript functionality

// Theme management
function toggleTheme() {
    const currentTheme = localStorage.getItem('theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    
    const themeIcon = document.getElementById('themeIcon');
    const themeText = document.getElementById('themeText');
    
    if (newTheme === 'dark') {
        themeIcon.textContent = '☀️';
        themeText.textContent = 'Light Mode';
    } else {
        themeIcon.textContent = '🌙';
        themeText.textContent = 'Dark Mode';
    }
}

// Logout function
function logout() {
    // Clear all localStorage data except theme preference
    const theme = localStorage.getItem('theme');
    localStorage.clear();
    if (theme) {
        localStorage.setItem('theme', theme);
    }
    
    // Redirect to logout endpoint
    window.location.href = '/logout';
}

// Navigation functions
function backToMainMenu() {
    // Hide all sections first
    const sections = document.querySelectorAll('.section');
    sections.forEach(section => section.classList.add('hidden'));
    
    // Show only the main menu
    document.getElementById('mainMenu').classList.remove('hidden');
}

function showLoginScreen() {
    // Hide logout button
    const logoutBtn = document.querySelector('.logout-btn');
    if (logoutBtn) {
        logoutBtn.style.display = 'none';
    }
}

function showLoggedInScreen() {
    // Show logout button
    const logoutBtn = document.querySelector('.logout-btn');
    if (logoutBtn) {
        logoutBtn.style.display = 'block';
    }
}

// Utility functions
function getCurrentNYTime() {
    const now = new Date();
    const nyTime = new Date(now.toLocaleString("en-US", {timeZone: "America/New_York"}));
    return nyTime.toISOString().slice(0, 16);
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Initialize theme
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    
    const themeIcon = document.getElementById('themeIcon');
    const themeText = document.getElementById('themeText');
    
    if (savedTheme === 'dark') {
        themeIcon.textContent = '☀️';
        themeText.textContent = 'Light Mode';
    } else {
        themeIcon.textContent = '🌙';
        themeText.textContent = 'Dark Mode';
    }
    
    // Show logged in screen
    showLoggedInScreen();
});
