// Toggle sidebar
document.getElementById('sidebarToggle').addEventListener('click', function() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');
    const icon = this.querySelector('i');
    
    sidebar.classList.toggle('collapsed');
    mainContent.classList.toggle('collapsed');
    
    if (sidebar.classList.contains('collapsed')) {
        icon.className = 'fas fa-chevron-right';
    } else {
        icon.className = 'fas fa-chevron-left';
    }
});

// Submenu functionality
document.querySelectorAll('.nav-item.has-submenu').forEach(item => {
    const link = item.querySelector('.nav-link');
    const submenu = item.querySelector('.submenu');
    
    link.addEventListener('click', function(e) {
        e.preventDefault();
        
        // Close other submenus
        document.querySelectorAll('.nav-item.has-submenu').forEach(otherItem => {
            if (otherItem !== item) {
                otherItem.classList.remove('open');
                otherItem.querySelector('.submenu').classList.remove('open');
            }
        });
        
        // Toggle current submenu
        item.classList.toggle('open');
        submenu.classList.toggle('open');
    });
});

// Chart configuration
const ctx = document.getElementById('performanceChart').getContext('2d');
const performanceChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin'],
        datasets: [
            {
                label: 'Projets terminés',
                data: [12, 19, 15, 22, 28, 24],
                borderColor: '#0052CC',
                backgroundColor: 'rgba(0, 82, 204, 0.1)',
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#0052CC',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2,
                pointRadius: 6
            },
            {
                label: 'Tâches complétées',
                data: [65, 89, 72, 95, 118, 156],
                borderColor: '#36B37E',
                backgroundColor: 'rgba(54, 179, 126, 0.1)',
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#36B37E',
                pointBorderColor: '#ffffff',
                pointBorderWidth: 2,
                pointRadius: 6
            }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'top',
                labels: {
                    usePointStyle: true,
                    padding: 20,
                    font: {
                        size: 14
                    }
                }
            },
            tooltip: {
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                titleColor: '#ffffff',
                bodyColor: '#ffffff',
                borderColor: '#0052CC',
                borderWidth: 1,
                cornerRadius: 8,
                displayColors: true,
                intersect: false,
                mode: 'index'
            }
        },
        scales: {
            x: {
                grid: {
                    display: false
                },
                ticks: {
                    font: {
                        size: 12
                    },
                    color: '#5E6C84'
                }
            },
            y: {
                beginAtZero: true,
                grid: {
                    color: '#DFE1E6',
                    drawBorder: false
                },
                ticks: {
                    font: {
                        size: 12
                    },
                    color: '#5E6C84'
                }
            }
        },
        interaction: {
            intersect: false,
            mode: 'index'
        },
        elements: {
            line: {
                borderWidth: 3
            }
        }
    }
});

// Après l'initialisation du premier graphique

// Graphique d'utilisation des API
const apiUsageCtx = document.getElementById('apiUsageChart');
if (apiUsageCtx) {
    new Chart(apiUsageCtx, {
        type: 'bar',
        data: {
            labels: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
            datasets: [{
                label: 'Requêtes API',
                data: [125000, 85000, 42000, 18000, 15000],
                backgroundColor: [
                    'rgba(0, 82, 204, 0.8)',
                    'rgba(54, 179, 126, 0.8)',
                    'rgba(255, 171, 0, 0.8)',
                    'rgba(255, 86, 48, 0.8)',
                    'rgba(100, 100, 255, 0.8)'
                ],
                borderColor: [
                    'rgba(0, 82, 204, 1)',
                    'rgba(54, 179, 126, 1)',
                    'rgba(255, 171, 0, 1)',
                    'rgba(255, 86, 48, 1)',
                    'rgba(100, 100, 255, 1)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.parsed.y.toLocaleString()} requêtes`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return value >= 1000 ? value/1000 + 'k' : value;
                        }
                    }
                }
            }
        }
    });
}

// Graphique de performance des workflows
const workflowCtx = document.getElementById('workflowPerformanceChart');
if (workflowCtx) {
    new Chart(workflowCtx, {
        type: 'doughnut',
        data: {
            labels: ['Complétés', 'En retard', 'En avance'],
            datasets: [{
                data: [65, 15, 20],
                backgroundColor: [
                    'rgba(0, 82, 204, 0.8)',
                    'rgba(255, 86, 48, 0.8)',
                    'rgba(54, 179, 126, 0.8)'
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.label}: ${context.raw}%`;
                        }
                    }
                }
            }
        }
    });
}

// Graphique des temps d'exécution
const durationCtx = document.getElementById('taskDurationChart');
if (durationCtx) {
    new Chart(durationCtx, {
        type: 'bar',
        data: {
            labels: ['Validation', 'Transformation', 'Enrichissement', 'Publication', 'Notification'],
            datasets: [
                {
                    label: 'Temps moyen',
                    data: [120, 85, 150, 65, 45],
                    backgroundColor: 'rgba(0, 82, 204, 0.6)'
                },
                {
                    label: 'Temps max',
                    data: [180, 120, 210, 95, 70],
                    backgroundColor: 'rgba(255, 86, 48, 0.6)'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    stacked: false,
                    grid: {
                        display: false
                    }
                },
                y: {
                    stacked: false,
                    title: {
                        display: true,
                        text: 'Temps (secondes)'
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${context.raw}s`;
                        }
                    }
                }
            }
        }
    });
}

// Gestion des onglets
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        // Ici vous pourriez ajouter la logique pour changer le contenu des onglets
    });
});

// Filtres temporels
document.querySelectorAll('.time-filter .filter-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.time-filter .filter-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        // Ici vous pourriez ajouter la logique pour filtrer les données
    });
});

// Options de vue
document.querySelectorAll('.view-options .btn-icon').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.view-options .btn-icon').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        // Ici vous pourriez ajouter la logique pour changer la vue
    });
});



// Hover effects for project cards
document.querySelectorAll('.project-card').forEach(card => {
    card.addEventListener('mouseenter', function() {
        this.style.transform = 'translateY(-4px)';
        this.style.boxShadow = '0 8px 24px rgba(0, 0, 0, 0.15)';
    });
    
    card.addEventListener('mouseleave', function() {
        this.style.transform = 'translateY(0)';
        this.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.05)';
    });
});

// Smooth animations on page load
window.addEventListener('load', function() {
    document.querySelectorAll('.metric-card').forEach((card, index) => {
        setTimeout(() => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            card.style.animation = `slideInUp 0.5s ease-out ${index * 0.1}s forwards`;
        }, 100);
    });
});

// Interactive tooltips
document.querySelectorAll('[data-tooltip]').forEach(element => {
    element.addEventListener('mouseenter', function() {
        this.style.position = 'relative';
    });
});

// Auto-hide notifications (if any)
setTimeout(() => {
    const notifications = document.querySelectorAll('.notification');
    notifications.forEach(notification => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
    });
}, 5000);

// Real-time clock update (optional)
function updateClock() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('fr-FR');
    const clockElement = document.getElementById('clock');
    if (clockElement) {
        clockElement.textContent = timeString;
    }
}

setInterval(updateClock, 1000);
updateClock();