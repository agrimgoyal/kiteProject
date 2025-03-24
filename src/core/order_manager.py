# src/core/order_manager.py
import logging
import threading
import queue
import time
from datetime import datetime
import json
import os
from typing import Dict, List, Optional, Any, Tuple, Set, Callable
from kiteconnect import KiteConnect

class OrderCounter:
    """Thread-safe order counter"""
    
    def __init__(self, count_file: str):
        self.count_file = count_file
        self.daily_counts = {}
        self.lock = threading.RLock()
        self.load_counts()
    
    def load_counts(self) -> None:
        """Load existing order counts from file"""
        if os.path.exists(self.count_file):
            try:
                with open(self.count_file, 'r') as f:
                    self.daily_counts = json.load(f)
            except Exception as e:
                logging.error(f"Error loading order count file: {e}")
                self.daily_counts = {}
    
    def save_counts(self) -> None:
        """Save current order counts to file"""
        try:
            with open(self.count_file, 'w') as f:
                json.dump(self.daily_counts, f)
        except Exception as e:
            logging.error(f"Error saving order count file: {e}")
    
    def get_today_count(self) -> int:
        """Get the count for today"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self.lock:
            return self.daily_counts.get(today, 0)
    
    def increment_count(self) -> int:
        """Increment today's count and return the new value"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self.lock:
            if today not in self.daily_counts:
                self.daily_counts[today] = 0
            self.daily_counts[today] += 1
            self.save_counts()
            return self.daily_counts[today]


class OrderManager:
    """Efficient order manager with queuing and rate limiting"""
    
    def __init__(self, api_key: str, api_secret: str, access_token: str, 
                 max_orders_per_day: int = 3000, 
                 order_alert_threshold: int = 2550,
                 test_mode: bool = True,
                 order_count_file: str = "order_count.json"):
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.max_orders_per_day = max_orders_per_day
        self.order_alert_threshold = order_alert_threshold
        self.test_mode = test_mode
        
        # Initialize Kite Connect client
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
        
        # Order counter
        self.order_counter = OrderCounter(order_count_file)
        
        # Order queue for rate limiting
        self.order_queue = queue.Queue()
        
        # Order placement thread
        self.order_thread = None
        self.is_running = False
        
        # Track active GTT orders
        self.active_gtt_orders = {}
        self.gtt_lock = threading.RLock()
        
        # GTT mappings for recovery
        self.gtt_mappings = {}
        self.load_gtt_mappings()
    
    def start(self) -> bool:
        """Start the order manager"""
        if self.is_running:
            return True
            
        self.is_running = True
        
        # Start order processing thread
        self.order_thread = threading.Thread(
            target=self._order_processor,
            daemon=True,
            name="OrderProcessor"
        )
        self.order_thread.start()
        
        # Log current order count at startup
        today_count = self.order_counter.get_today_count()
        logging.info(f"Starting with {today_count} orders already sent today (max: {self.max_orders_per_day})")
        
        if today_count >= self.max_orders_per_day:
            logging.critical(f"ALERT: Daily order limit of {self.max_orders_per_day} already reached! System will not place new orders.")
            
        return True
    
    def stop(self) -> None:
        """Stop the order manager"""
        self.is_running = False
        
        # Wait for order thread to finish
        if self.order_thread and self.order_thread.is_alive():
            self.order_thread.join(timeout=1.0)
    
    def check_order_limit(self) -> bool:
        """Check if we've hit the order limit"""
        today_count = self.order_counter.get_today_count()
        max_orders = self.max_orders_per_day
        
        if today_count >= max_orders:
            logging.critical(f"ALERT: Daily order limit of {max_orders} reached! No more orders will be placed today.")
            return False
        
        if today_count >= self.order_alert_threshold:
            logging.warning(f"ALERT: Order count ({today_count}) approaching daily limit of {max_orders}!")
        
        return True
    
    def place_gtt_order(self, symbol: str, exchange: str, trigger_price: float, target_price: float, 
                        trade_type: str, quantity: int, product_type: str, 
                        signal_id: str = "", row_idx: int = -1, unique_tag: str = "") -> Optional[int]:
        """Queue a GTT order for placement"""
        # First check order limit
        if not self.check_order_limit():
            logging.error(f"Cannot place GTT order for {symbol} - daily order limit reached")
            return None
        
        # Prepare order details
        order_details = {
            "type": "gtt",
            "symbol": symbol,
            "exchange": exchange,
            "trigger_price": trigger_price,
            "target_price": target_price,
            "trade_type": trade_type,
            "quantity": quantity,
            "product_type": product_type,
            "signal_id": signal_id,
            "row_idx": row_idx,
            "unique_tag": unique_tag,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Queue the order
        self.order_queue.put(order_details)
        
        if self.test_mode:
            logging.info(f"TEST MODE: Would place GTT for {symbol} at trigger {trigger_price}, target {target_price}")
            return -1  # Return a dummy ID for test mode
            
        return 0  # Will be replaced with actual ID when processed
    
    def _order_processor(self) -> None:
        """Background thread to process order queue"""
        while self.is_running:
            try:
                # Get an order from the queue
                order_details = self.order_queue.get(timeout=0.5)
                
                # Process the order based on type
                if order_details["type"] == "gtt":
                    self._process_gtt_order(order_details)
                elif order_details["type"] == "direct":
                    self._process_direct_order(order_details)
                
                # Mark as done
                self.order_queue.task_done()
                
                # Rate limiting for API calls
                time.sleep(0.2)
                
            except queue.Empty:
                # No orders to process
                pass
            except Exception as e:
                logging.error(f"Error processing order: {e}", exc_info=True)
                # Sleep to prevent error spam
                time.sleep(1.0)
    
    def _process_gtt_order(self, order_details: Dict[str, Any]) -> Optional[int]:
        """Process a GTT order placement"""
        if self.test_mode:
            # In test mode, just log and return a dummy ID
            logging.info(f"TEST MODE: Would place GTT for {order_details['symbol']} "
                         f"at trigger {order_details['trigger_price']}, target {order_details['target_price']}")
            return -1
            
        try:
            # Ensure we're under the order limit
            if not self.check_order_limit():
                logging.error(f"Cannot place GTT order for {order_details['symbol']} - daily order limit reached")
                return None
                
            # Extract order parameters
            symbol = order_details["symbol"]
            exchange = order_details["exchange"]
            trigger_price = order_details["trigger_price"]
            target_price = order_details["target_price"]
            trade_type = order_details["trade_type"]
            quantity = order_details["quantity"]
            product_type = order_details["product_type"]
            unique_tag = order_details.get("unique_tag", "")
            signal_id = order_details.get("signal_id", "")
            row_idx = order_details.get("row_idx", -1)
            
            # Set transaction type based on trade type
            transaction_type = "SELL" if trade_type == "SHORT" else "BUY"
            
            # Define the GTT trigger
            trigger_params = {
                "trigger_type": "single",
                "exchange": exchange,
                "tradingsymbol": symbol,
                "trigger_values": [trigger_price],
                "last_price": 0,  # Will be updated with current price
                "orders": [{
                    "exchange": exchange,
                    "tradingsymbol": symbol,
                    "transaction_type": transaction_type,
                    "quantity": quantity,
                    "order_type": "LIMIT",
                    "product": product_type,
                    "price": target_price,
                    "tag": unique_tag
                }]
            }
            
            # Update last_price if we have access to market data
            # For now, using a dummy value - should be updated with actual price
            trigger_params["last_price"] = trigger_price * 0.99 if trade_type == "SHORT" else trigger_price * 1.01
            
            # Place the GTT order
            response = self.kite.place_gtt(**trigger_params)
            gtt_id = response.get("trigger_id")
            
            # Increment order count
            new_count = self.order_counter.increment_count()
            
            # Log placement with all identifying information
            logging.info(f"GTT order placed for {symbol} (row {row_idx}) - ID: {gtt_id}, Type: {transaction_type}")
            logging.info(f"Order count incremented to {new_count}/{self.max_orders_per_day} for today")
            
            # Save mapping for recovery
            self.save_gtt_mapping(gtt_id, signal_id, row_idx, symbol)
            
            # Update active GTT orders
            with self.gtt_lock:
                self.active_gtt_orders[gtt_id] = {
                    "symbol": symbol,
                    "transaction_type": transaction_type,
                    "trigger_price": trigger_price,
                    "target_price": target_price,
                    "quantity": quantity,
                    "product_type": product_type,
                    "exchange": exchange,
                    "placed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "row_index": row_idx,
                    "signal_id": signal_id
                }
            
            return gtt_id
                
        except Exception as e:
            logging.error(f"Error placing GTT order for {order_details['symbol']}: {e}")
            return None
    
    def _process_direct_order(self, order_details: Dict[str, Any]) -> Optional[int]:
        """Process a direct order placement"""
        # Implementation similar to _process_gtt_order but for direct orders
        pass
    
    def save_gtt_mapping(self, gtt_id: int, signal_id: str, row_idx: int, symbol: str) -> None:
        """Save GTT to signal mapping to a file"""
        mapping_file = "gtt_mappings.json"
        
        try:
            # Load existing mappings
            if os.path.exists(mapping_file):
                with open(mapping_file, 'r') as f:
                    mappings = json.load(f)
            else:
                mappings = {}
            
            # Add or update mapping
            mappings[str(gtt_id)] = {
                "signal_id": signal_id,
                "row_idx": int(row_idx),
                "symbol": symbol,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Save updated mappings
            with open(mapping_file, 'w') as f:
                json.dump(mappings, f)
                
            # Update in-memory mappings
            self.gtt_mappings = mappings
                
        except Exception as e:
            logging.error(f"Error saving GTT mapping: {e}")
    
    def load_gtt_mappings(self) -> None:
        """Load GTT mappings from file"""
        mapping_file = "gtt_mappings.json"
        
        try:
            if os.path.exists(mapping_file):
                with open(mapping_file, 'r') as f:
                    self.gtt_mappings = json.load(f)
                logging.info(f"Loaded {len(self.gtt_mappings)} GTT mappings")
            else:
                self.gtt_mappings = {}
        except Exception as e:
            logging.error(f"Error loading GTT mappings: {e}")
            self.gtt_mappings = {}
    
    def verify_gtt_orders(self) -> Dict[int, Any]:
        """Verify the status of all GTT orders"""
        if self.test_mode:
            return {}
            
        try:
            # Get all GTT orders from Kite
            gtt_orders = self.kite.get_gtts()
            
            # Build a dictionary of active orders
            active_orders = {int(order["id"]): order for order in gtt_orders}
            
            # Update our tracking of active orders
            with self.gtt_lock:
                self.active_gtt_orders = {
                    order_id: self.active_gtt_orders.get(order_id, {})
                    for order_id in active_orders.keys()
                }
            
            return active_orders
                
        except Exception as e:
            logging.error(f"Error verifying GTT orders: {e}")
            return {}
    
    def delete_gtt_order(self, gtt_id: int) -> bool:
        """Delete a GTT order by ID"""
        if self.test_mode:
            logging.info(f"TEST MODE: Would delete GTT order {gtt_id}")
            return True
            
        try:
            self.kite.delete_gtt(gtt_id)
            logging.info(f"Deleted GTT order {gtt_id}")
            
            # Remove from our tracking dict
            with self.gtt_lock:
                if gtt_id in self.active_gtt_orders:
                    del self.active_gtt_orders[gtt_id]
                    
            return True
        except Exception as e:
            logging.error(f"Error deleting GTT order {gtt_id}: {e}")
            return False