// Inspection-specific JavaScript functionality

// Global variables
let currentPage = 1;
let totalPages = 1;
let currentInspections = [];

// Main menu functions
function showInspectedVans() {
    // Hide all sections first
    const sections = document.querySelectorAll('.section');
    sections.forEach(section => section.classList.add('hidden'));
    
    // Show inspected vans section
    document.getElementById('inspectedVansSection').classList.remove('hidden');
    
    // Load the data
    loadInspectedVans();
}

function startInspection() {
    // Set flag to track that we came from New Inspection
    localStorage.setItem('eventSelectionSource', 'newInspection');
    document.getElementById("mainMenu").classList.add("hidden");
    document.getElementById("eventSelectionSection").classList.remove("hidden");
    loadEvents();
}

function openAttachVideos() {
    // Check for missing videos first
    fetch('/missing_videos')
        .then(response => response.json())
        .then(missingVideos => {
            if (missingVideos.length === 0) {
                // No missing videos - show message
                document.getElementById("mainMenu").classList.add("hidden");
                document.getElementById("attachVideosSection").classList.remove("hidden");
                
                // Show message that all videos are attached
                const missingList = document.getElementById('missingList');
                const attachForm = document.getElementById('attachForm');
                
                if (missingList) {
                    missingList.innerHTML = '<div class="alert alert-success">✅ All inspections have videos attached!</div>';
                }
                
                if (attachForm) {
                    attachForm.classList.add('hidden');
                }
            } else {
                // There are missing videos - proceed with event selection
                document.getElementById("mainMenu").classList.add("hidden");
                document.getElementById("eventSelectionAttachSection").classList.remove("hidden");
                loadEventsForAttach();
            }
        })
        .catch(error => {
            console.error('Error checking missing videos:', error);
            // On error, proceed with normal flow
            document.getElementById("mainMenu").classList.add("hidden");
            document.getElementById("eventSelectionAttachSection").classList.remove("hidden");
            loadEventsForAttach();
        });
}

// Event selection functions
function loadEvents() {
    fetch('/events')
        .then(response => response.json())
        .then(events => {
            const eventList = document.getElementById('eventList');
            eventList.innerHTML = '';
            
            events.forEach(event => {
                const eventItem = document.createElement('div');
                eventItem.className = 'event-item';
                eventItem.innerHTML = `
                    <label>
                        <input type="radio" name="event" value="${event.name}">
                        ${event.name}
                    </label>
                `;
                eventList.appendChild(eventItem);
            });
            
            // Add "Create New Event" option
            const newEventItem = document.createElement('div');
            newEventItem.className = 'event-item';
            newEventItem.innerHTML = `
                <label>
                    <input type="radio" name="event" value="create_new">
                    Other - Create New Event
                </label>
            `;
            eventList.appendChild(newEventItem);
        })
        .catch(error => {
            console.error('Error loading events:', error);
            document.getElementById('eventList').innerHTML = '<p>Error loading events. Please try again.</p>';
        });
}

function loadEventsForAttach() {
    fetch('/events')
        .then(response => response.json())
        .then(events => {
            const eventList = document.getElementById('eventListAttach');
            eventList.innerHTML = '';
            
            events.forEach(event => {
                const eventItem = document.createElement('div');
                eventItem.className = 'event-item';
                eventItem.innerHTML = `
                    <label>
                        <input type="radio" name="eventAttach" value="${event.name}">
                        ${event.name}
                    </label>
                `;
                eventList.appendChild(eventItem);
            });
        })
        .catch(error => {
            console.error('Error loading events:', error);
            document.getElementById('eventListAttach').innerHTML = '<p>Error loading events. Please try again.</p>';
        });
}

function proceedToEventSelection() {
    const selectedEvent = document.querySelector('input[name="event"]:checked');
    if (!selectedEvent) {
        alert('Please select an event');
        return;
    }
    
    if (selectedEvent.value === 'create_new') {
        const newEventName = prompt('Enter new event name:');
        if (!newEventName || newEventName.trim() === '') {
            return;
        }
        
        // Create new event
        fetch('/events', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name: newEventName.trim() })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Set the event name and proceed
                document.getElementById('event_name').value = newEventName.trim();
                localStorage.setItem('selectedEvent', newEventName.trim());
                proceedToInspectionForm();
            } else {
                alert('Error creating event: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Error creating event:', error);
            alert('Error creating event. Please try again.');
        });
    } else {
        // Use existing event
        document.getElementById('event_name').value = selectedEvent.value;
        localStorage.setItem('selectedEvent', selectedEvent.value);
        proceedToInspectionForm();
    }
}

function proceedToEventSelectionAttach() {
    const selectedEvent = document.querySelector('input[name="eventAttach"]:checked');
    if (!selectedEvent) {
        alert('Please select an event');
        return;
    }
    
    // Proceed to video attachment
    window.location.href = `/attach_videos?event=${encodeURIComponent(selectedEvent.value)}`;
}

function proceedToInspectionForm() {
    // Hide event selection
    document.getElementById('eventSelectionSection').classList.add('hidden');
    
    // Show inspection form
    document.getElementById('inspectionFormSection').classList.remove('hidden');
    
    // Set current date/time
    document.getElementById('dateField').value = getCurrentNYTime();
    
    // Load COV options
    loadCOVOptions();
}

// COV loading
function loadCOVOptions() {
    fetch('/covs')
        .then(response => response.json())
        .then(covs => {
            const vanSelect = document.getElementById('van_number');
            vanSelect.innerHTML = '<option value="">Select COV</option>';
            
            covs.forEach(cov => {
                const option = document.createElement('option');
                option.value = cov.number;
                option.textContent = `COV ${cov.number}`;
                vanSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error loading COVs:', error);
        });
}

// Inspected vans list functions
function loadInspectedVans() {
    const sortBy = document.getElementById('sortBy').value;
    const perPage = document.getElementById('perPage').value;
    
    fetch(`/inspected_vans?page=${currentPage}&per_page=${perPage}&sort=${sortBy}`)
        .then(response => response.json())
        .then(data => {
            currentInspections = data.inspections;
            totalPages = data.total_pages;
            displayInspectedVans(data.inspections);
            updatePagination();
        })
        .catch(error => {
            console.error('Error loading inspected vans:', error);
            document.getElementById('inspectedVansList').innerHTML = '<p>Error loading data. Please try again.</p>';
        });
}

function displayInspectedVans(inspections) {
    const container = document.getElementById('inspectedVansList');
    
    if (inspections.length === 0) {
        container.innerHTML = '<p class="text-center text-muted">No inspections found.</p>';
        return;
    }
    
    container.innerHTML = inspections.map(inspection => `
        <div class="inspection-card">
            <div class="inspection-header">
                <div class="inspection-info">
                    <div class="inspection-title">COV ${inspection.van_number}</div>
                    <div class="inspection-meta">
                        <span>📅 ${new Date(inspection.date).toLocaleDateString()}</span>
                        <span>🕐 ${new Date(inspection.date).toLocaleTimeString()}</span>
                        <span>👤 ${inspection.inspector_id}</span>
                        <span>🎯 ${inspection.event_name || 'No Event'}</span>
                        <span>📊 ${inspection.odometer_in || 'N/A'} mi</span>
                    </div>
                </div>
                <div class="video-section">
                    ${inspection.video_filename ? 
                        `<img src="/thumbnail/${inspection.video_filename.replace(/\.[^/.]+$/, '.jpg')}" 
                             alt="Video thumbnail" 
                             class="video-thumbnail" 
                             onclick="playVideo('${inspection.video_filename}')">` : 
                        '<span class="text-muted">No video</span>'
                    }
                </div>
            </div>
        </div>
    `).join('');
}

function updatePagination() {
    const container = document.getElementById('pagination');
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }
    
    let html = '';
    
    // Previous button
    html += `<button ${currentPage === 1 ? 'disabled' : ''} onclick="changePage(${currentPage - 1})">Previous</button>`;
    
    // Page numbers
    for (let i = 1; i <= totalPages; i++) {
        if (i === currentPage) {
            html += `<button class="current-page">${i}</button>`;
        } else {
            html += `<button onclick="changePage(${i})">${i}</button>`;
        }
    }
    
    // Next button
    html += `<button ${currentPage === totalPages ? 'disabled' : ''} onclick="changePage(${currentPage + 1})">Next</button>`;
    
    container.innerHTML = html;
}

function changePage(page) {
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    loadInspectedVans();
}

// Video functions
function playVideo(filename) {
    // Open video in new window/tab
    window.open(`/video/${filename}`, '_blank');
}

// Navigation back functions
function backFromEventSelection() {
    const source = localStorage.getItem('eventSelectionSource');
    localStorage.removeItem('eventSelectionSource');
    
    // Hide event selection section
    document.getElementById("eventSelectionSection").classList.add("hidden");
    
    if (source === 'newInspection') {
        // Came from New Inspection - go back to main menu
        document.getElementById("mainMenu").classList.remove("hidden");
    } else {
        // Came from CAPID confirmation - go back to confirm section
        document.getElementById("confirmSection").classList.remove("hidden");
        showLoggedInScreen();
    }
}

function backToMainMenuFromEventAttach() {
    // Hide all sections first
    const sections = document.querySelectorAll('.section');
    sections.forEach(section => section.classList.add('hidden'));
    
    // Show only the main menu
    document.getElementById("mainMenu").classList.remove("hidden");
}

// Step navigation
function goToStep(step) {
    // This would be implemented for the inspection form steps
    console.log('Going to step:', step);
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Set current date/time for inspection form
    const dateField = document.getElementById('dateField');
    if (dateField) {
        dateField.value = getCurrentNYTime();
    }
});
