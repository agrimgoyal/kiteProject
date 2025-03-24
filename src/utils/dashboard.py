# src/utils/dashboard.py
"""
Real-time dashboard for monitoring trading activity
Accessible via a simple web UI
"""
import threading
import time
import logging
import json
import os
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

class DashboardData:
    """Stores data for the dashboard"""
    
    def __init__(self):
        self.data = {
            "system_status": {
                "status": "starting",
                "uptime": 0,
                "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "memory_usage_mb": 0,
                "cpu_usage": 0
            },
            "trading_status": {
                "test_mode": True,
                "active_symbols": 0,
                "symbols_with_prices": 0,
                "active_gtt_orders": 0,
                "orders_today": 0,
                "max_orders_per_day": 3000
            },
            "market_data": {
                "connection_status": "disconnected",
                "last_tick_time": "",
                "total_ticks_received": 0,
                "symbols_subscribed": 0
            },
            "order_manager": {
                "pending_orders": 0,
                "completed_orders": 0,
                "failed_orders": 0
            },
            "recent_events": [],
            "active_orders": {},
            "potential_triggers": []
        }
        self.lock = threading.RLock()
    
    def update(self, section, key, value):
        """Update a specific data point"""
        with self.lock:
            if section in self.data and key in self.data[section]:
                self.data[section][key] = value
    
    def update_section(self, section, data_dict):
        """Update an entire section"""
        with self.lock:
            if section in self.data:
                self.data[section].update(data_dict)
    
    def add_event(self, event_type, message):
        """Add an event to the recent events list"""
        with self.lock:
            event = {
                "type": event_type,
                "message": message,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            self.data["recent_events"].insert(0, event)
            # Keep only the most recent 100 events
            self.data["recent_events"] = self.data["recent_events"][:100]
    
    def update_active_order(self, order_id, order_data):
        """Update data for an active order"""
        with self.lock:
            self.data["active_orders"][order_id] = order_data
    
    def remove_active_order(self, order_id):
        """Remove an order from active orders"""
        with self.lock:
            if order_id in self.data["active_orders"]:
                del self.data["active_orders"][order_id]
    
    def update_potential_triggers(self, triggers):
        """Update list of potential triggers"""
        with self.lock:
            self.data["potential_triggers"] = triggers
    
    def get_data(self):
        """Get a copy of the current data"""
        with self.lock:
            return dict(self.data)

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread"""
    daemon_threads = True

class DashboardHandler(SimpleHTTPRequestHandler):
    """Handler for dashboard HTTP requests"""
    
    def __init__(self, *args, dashboard_data=None, **kwargs):
        self.dashboard_data = dashboard_data
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/api/data':
            # Return dashboard data as JSON
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            if self.dashboard_data:
                data = self.dashboard_data.get_data()
                self.wfile.write(json.dumps(data).encode())
            else:
                self.wfile.write(json.dumps({"error": "No dashboard data available"}).encode())
        else:
            # Serve static files from the dashboard directory
            self.path = '/dashboard' + self.path
            
            if self.path == '/dashboard/':
                self.path = '/dashboard/index.html'
                
            try:
                return super().do_GET()
            except Exception as e:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(f"File not found: {e}".encode())

class Dashboard:
    """Real-time dashboard for the trading system"""
    
    def __init__(self, host='localhost', port=8080):
        self.host = host
        self.port = port
        self.dashboard_data = DashboardData()
        self.is_running = False
        self.server = None
        self.server_thread = None
        
        # Ensure dashboard directory exists
        os.makedirs('dashboard', exist_ok=True)
        
        # Create simple index.html if it doesn't exist
        if not os.path.exists('dashboard/index.html'):
            self._create_dashboard_files()
    
    def start(self):
        """Start the dashboard server"""
        if self.is_running:
            return False
            
        try:
            # Create handler with access to dashboard data
            handler = lambda *args, **kwargs: DashboardHandler(*args, dashboard_data=self.dashboard_data, **kwargs)
            
            # Start HTTP server
            self.server = ThreadingHTTPServer((self.host, self.port), handler)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            
            self.is_running = True
            logging.info(f"Dashboard started at http://{self.host}:{self.port}/")
            
            return True
        except Exception as e:
            logging.error(f"Error starting dashboard: {e}")
            return False
    
    def stop(self):
        """Stop the dashboard server"""
        if not self.is_running:
            return
            
        self.is_running = False
        
        if self.server:
            self.server.shutdown()
            self.server = None
            
        if self.server_thread:
            self.server_thread.join(timeout=1.0)
            self.server_thread = None
            
        logging.info("Dashboard stopped")
    
    def update(self, section, key, value):
        """Update a data point on the dashboard"""
        self.dashboard_data.update(section, key, value)
    
    def update_section(self, section, data_dict):
        """Update an entire section of the dashboard"""
        self.dashboard_data.update_section(section, data_dict)
    
    def add_event(self, event_type, message):
        """Add an event to the dashboard"""
        self.dashboard_data.add_event(event_type, message)
    
    def update_active_order(self, order_id, order_data):
        """Update an active order on the dashboard"""
        self.dashboard_data.update_active_order(order_id, order_data)
    
    def remove_active_order(self, order_id):
        """Remove an active order from the dashboard"""
        self.dashboard_data.remove_active_order(order_id)
    
    def update_potential_triggers(self, triggers):
        """Update potential triggers on the dashboard"""
        self.dashboard_data.update_potential_triggers(triggers)
    
    def _create_dashboard_files(self):
        """Create basic dashboard HTML and JavaScript files"""
        # Create index.html
        index_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KiteTrader Dashboard</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <style>
        body { padding-top: 20px; }
        .card { margin-bottom: 20px; }
        .event-info { color: #0d6efd; }
        .event-warning { color: #ffc107; }
        .event-error { color: #dc3545; }
        .event-success { color: #198754; }
    </style>
</head>
<body>
    <div class="container">
        <header class="pb-3 mb-4 border-bottom">
            <h1 class="display-6">KiteTrader Dashboard</h1>
            <div class="d-flex justify-content-between">
                <div>Status: <span id="system-status" class="badge bg-secondary">Unknown</span></div>
                <div>Last Updated: <span id="last-update">Never</span></div>
            </div>
        </header>

        <div class="row">
            <!-- System Status -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">System Status</div>
                    <div class="card-body">
                        <ul class="list-group list-group-flush" id="system-status-list">
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Status:</span><span id="status">Unknown</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Uptime:</span><span id="uptime">0s</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Memory Usage:</span><span id="memory">0 MB</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>CPU Usage:</span><span id="cpu">0%</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>

            <!-- Trading Status -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Trading Status</div>
                    <div class="card-body">
                        <ul class="list-group list-group-flush" id="trading-status-list">
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Mode:</span><span id="test-mode">Test</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Active Symbols:</span><span id="active-symbols">0</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Active GTT Orders:</span><span id="active-gtt-orders">0</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Orders Today:</span><span id="orders-today">0/0</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <!-- Market Data -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Market Data</div>
                    <div class="card-body">
                        <ul class="list-group list-group-flush" id="market-data-list">
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Connection:</span><span id="connection-status">Disconnected</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Last Tick:</span><span id="last-tick-time">Never</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Total Ticks:</span><span id="total-ticks">0</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Subscribed Symbols:</span><span id="symbols-subscribed">0</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>

            <!-- Order Manager -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Order Manager</div>
                    <div class="card-body">
                        <ul class="list-group list-group-flush" id="order-manager-list">
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Pending Orders:</span><span id="pending-orders">0</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Completed Orders:</span><span id="completed-orders">0</span>
                            </li>
                            <li class="list-group-item d-flex justify-content-between">
                                <span>Failed Orders:</span><span id="failed-orders">0</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <!-- Recent Events -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Recent Events</div>
                    <div class="card-body">
                        <div class="list-group" id="recent-events">
                            <div class="list-group-item">No events yet</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Potential Triggers -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Potential Triggers</div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped table-sm">
                                <thead>
                                    <tr>
                                        <th>Symbol</th>
                                        <th>Current Price</th>
                                        <th>Target Price</th>
                                        <th>Type</th>
                                    </tr>
                                </thead>
                                <tbody id="potential-triggers">
                                    <tr>
                                        <td colspan="4" class="text-center">No potential triggers</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Active Orders -->
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">Active Orders</div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped">
                                <thead>
                                    <tr>
                                        <th>Order ID</th>
                                        <th>Symbol</th>
                                        <th>Type</th>
                                        <th>Quantity</th>
                                        <th>Price</th>
                                        <th>Status</th>
                                        <th>Time</th>
                                    </tr>
                                </thead>
                                <tbody id="active-orders">
                                    <tr>
                                        <td colspan="7" class="text-center">No active orders</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="dashboard.js"></script>
</body>
</html>
"""

        # Create dashboard.js
        dashboard_js = """// Dashboard updater
document.addEventListener('DOMContentLoaded', function() {
    // Update interval in milliseconds
    const UPDATE_INTERVAL = 1000;
    
    // Start updating the dashboard
    updateDashboard();
    setInterval(updateDashboard, UPDATE_INTERVAL);
    
    function updateDashboard() {
        fetch('/api/data')
            .then(response => response.json())
            .then(data => {
                updateUI(data);
                document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
            })
            .catch(error => {
                console.error('Error fetching dashboard data:', error);
            });
    }
    
    function updateUI(data) {
        // System Status
        const systemStatus = data.system_status;
        document.getElementById('status').textContent = systemStatus.status;
        document.getElementById('uptime').textContent = formatUptime(systemStatus.uptime);
        document.getElementById('memory').textContent = systemStatus.memory_usage_mb.toFixed(1) + ' MB';
        document.getElementById('cpu').textContent = systemStatus.cpu_usage.toFixed(1) + '%';
        
        // Update status badge
        const statusBadge = document.getElementById('system-status');
        statusBadge.textContent = systemStatus.status;
        statusBadge.className = 'badge ' + getStatusBadgeClass(systemStatus.status);
        
        // Trading Status
        const tradingStatus = data.trading_status;
        document.getElementById('test-mode').textContent = tradingStatus.test_mode ? 'Test Mode' : 'Live Mode';
        document.getElementById('active-symbols').textContent = tradingStatus.active_symbols;
        document.getElementById('active-gtt-orders').textContent = tradingStatus.active_gtt_orders;
        document.getElementById('orders-today').textContent = 
            `${tradingStatus.orders_today}/${tradingStatus.max_orders_per_day}`;
        
        // Market Data
        const marketData = data.market_data;
        const connectionStatusElem = document.getElementById('connection-status');
        connectionStatusElem.textContent = marketData.connection_status;
        connectionStatusElem.className = 
            marketData.connection_status === 'connected' ? 'text-success' : 'text-danger';
        document.getElementById('last-tick-time').textContent = 
            marketData.last_tick_time || 'Never';
        document.getElementById('total-ticks').textContent = marketData.total_ticks_received;
        document.getElementById('symbols-subscribed').textContent = marketData.symbols_subscribed;
        
        // Order Manager
        const orderManager = data.order_manager;
        document.getElementById('pending-orders').textContent = orderManager.pending_orders;
        document.getElementById('completed-orders').textContent = orderManager.completed_orders;
        document.getElementById('failed-orders').textContent = orderManager.failed_orders;
        
        // Recent Events
        updateRecentEvents(data.recent_events);
        
        // Active Orders
        updateActiveOrders(data.active_orders);
        
        // Potential Triggers
        updatePotentialTriggers(data.potential_triggers);
    }
    
    function formatUptime(seconds) {
        const days = Math.floor(seconds / 86400);
        seconds %= 86400;
        const hours = Math.floor(seconds / 3600);
        seconds %= 3600;
        const minutes = Math.floor(seconds / 60);
        seconds = Math.floor(seconds % 60);
        
        let result = '';
        if (days > 0) result += days + 'd ';
        if (hours > 0) result += hours + 'h ';
        if (minutes > 0) result += minutes + 'm ';
        result += seconds + 's';
        
        return result;
    }
    
    function getStatusBadgeClass(status) {
        switch (status.toLowerCase()) {
            case 'running':
                return 'bg-success';
            case 'starting':
                return 'bg-warning';
            case 'stopped':
                return 'bg-danger';
            case 'error':
                return 'bg-danger';
            default:
                return 'bg-secondary';
        }
    }
    
    function updateRecentEvents(events) {
        const eventsContainer = document.getElementById('recent-events');
        if (!events || events.length === 0) {
            eventsContainer.innerHTML = '<div class="list-group-item">No events yet</div>';
            return;
        }
        
        eventsContainer.innerHTML = '';
        
        events.slice(0, 10).forEach(event => {
            const eventClass = `event-${event.type}`;
            const eventItem = document.createElement('div');
            eventItem.className = `list-group-item ${eventClass}`;
            eventItem.innerHTML = `<small class="text-muted">${event.timestamp}</small> ${event.message}`;
            eventsContainer.appendChild(eventItem);
        });
    }
    
    function updateActiveOrders(orders) {
        const ordersContainer = document.getElementById('active-orders');
        if (!orders || Object.keys(orders).length === 0) {
            ordersContainer.innerHTML = '<tr><td colspan="7" class="text-center">No active orders</td></tr>';
            return;
        }
        
        ordersContainer.innerHTML = '';
        
        Object.entries(orders).forEach(([orderId, order]) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${orderId}</td>
                <td>${order.symbol}</td>
                <td>${order.transaction_type}</td>
                <td>${order.quantity}</td>
                <td>${order.price}</td>
                <td>${order.status}</td>
                <td>${order.time}</td>
            `;
            ordersContainer.appendChild(tr);
        });
    }
    
    function updatePotentialTriggers(triggers) {
        const triggersContainer = document.getElementById('potential-triggers');
        if (!triggers || triggers.length === 0) {
            triggersContainer.innerHTML = '<tr><td colspan="4" class="text-center">No potential triggers</td></tr>';
            return;
        }
        
        triggersContainer.innerHTML = '';
        
        triggers.forEach(trigger => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${trigger.symbol}</td>
                <td>${trigger.current_price}</td>
                <td>${trigger.target_price}</td>
                <td>${trigger.trade_type}</td>
            `;
            triggersContainer.appendChild(tr);
        });
    }
});
"""

        # Write files
        with open('dashboard/index.html', 'w') as f:
            f.write(index_html)
            
        with open('dashboard/dashboard.js', 'w') as f:
            f.write(dashboard_js)