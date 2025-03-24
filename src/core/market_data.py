# src/core/market_data.py
import threading
import queue
import time
import logging
from typing import Dict, List, Callable, Set, Optional
from kiteconnect import KiteTicker

class PriceCache:
    """Thread-safe price cache without locks"""
    def __init__(self):
        self.prices = {}
        self.timestamps = {}
    
    def update(self, symbol: str, price: float) -> None:
        """Update price atomically"""
        self.prices[symbol] = price
        self.timestamps[symbol] = time.time()
    
    def update_batch(self, updates: Dict[str, float]) -> None:
        """Update multiple prices atomically"""
        for symbol, price in updates.items():
            self.prices[symbol] = price
            self.timestamps[symbol] = time.time()
    
    def get(self, symbol: str) -> Optional[float]:
        """Get price atomically"""
        return self.prices.get(symbol)
    
    def get_all(self) -> Dict[str, float]:
        """Get all prices atomically"""
        # Return a copy to prevent modification during iteration
        return dict(self.prices)


class MarketDataHandler:
    """Optimized market data handler with non-blocking design"""
    
    def __init__(self, api_key: str, access_token: str, token_to_symbol: Dict[int, str]):
        self.api_key = api_key
        self.access_token = access_token
        self.token_to_symbol = token_to_symbol
        self.symbol_to_token = {v: k for k, v in token_to_symbol.items()}
        
        # Efficient price storage
        self.price_cache = PriceCache()
        
        # Queue for processing price updates outside websocket thread
        self.price_queue = queue.Queue()
        self.trigger_check_queue = queue.Queue()
        
        # Callbacks
        self.on_price_update: Optional[Callable] = None
        self.on_potential_trigger: Optional[Callable] = None
        
        # Thread management
        self.is_running = False
        self.ticker: Optional[KiteTicker] = None
        self.processor_thread: Optional[threading.Thread] = None
        self.connected = False
        self.last_trigger_check = 0
        self.trigger_check_interval = 0.2  # seconds
    
    def start(self) -> bool:
        """Start the market data handler and processing threads"""
        if self.is_running:
            return True
            
        self.is_running = True
        
        # Start price processor thread
        self.processor_thread = threading.Thread(
            target=self._price_processor_loop,
            daemon=True,
            name="PriceProcessor"
        )
        self.processor_thread.start()
        
        # Initialize ticker
        self.ticker = KiteTicker(self.api_key, self.access_token)
        self.ticker.on_ticks = self._on_ticks
        self.ticker.on_connect = self._on_connect
        self.ticker.on_close = self._on_close
        self.ticker.on_error = self._on_error
        
        # Start ticker in a separate thread
        threading.Thread(
            target=self.ticker.connect,
            daemon=True,
            name="KiteTicker"
        ).start()
        
        return True
    
    def stop(self) -> None:
        """Stop the market data handler"""
        self.is_running = False
        
        if self.ticker:
            self.ticker.close()
            self.ticker = None
        
        # Processor threads will exit when is_running becomes False
    
    def update_token_to_symbol(self, token_to_symbol: Dict[int, str]) -> None:
        """Update token to symbol mapping"""
        self.token_to_symbol = token_to_symbol
        self.symbol_to_token = {v: k for k, v in token_to_symbol.items()}
        
        # Resubscribe if connected
        if self.connected and self.ticker:
            self.subscribe_tokens(list(token_to_symbol.keys()))
    
    def subscribe_tokens(self, tokens: List[int]) -> None:
        """Subscribe to instrument tokens"""
        if self.connected and self.ticker:
            self.ticker.subscribe(tokens)
            self.ticker.set_mode(self.ticker.MODE_FULL, tokens)
            logging.info(f"Subscribed to {len(tokens)} tokens")
    
    def _on_ticks(self, ws, ticks) -> None:
        """Optimized tick handler with minimal processing"""
        # Quick extraction of critical data with no locking
        price_updates = {}
        
        for tick in ticks:
            token = tick["instrument_token"]
            symbol = self.token_to_symbol.get(token)
            
            if symbol:
                price = tick.get("last_price")
                if price:
                    price_updates[symbol] = price
        
        # Only queue for processing if we have updates
        if price_updates:
            # Update our price cache immediately
            self.price_cache.update_batch(price_updates)
            
            # Queue the updates for further processing
            self.price_queue.put(price_updates)
            
            # Check if we should do a trigger check
            now = time.time()
            if now - self.last_trigger_check >= self.trigger_check_interval:
                self.trigger_check_queue.put(price_updates)
                self.last_trigger_check = now
    
    def _on_connect(self, ws, response) -> None:
        """Handle WebSocket connection"""
        logging.info("WebSocket connected")
        self.connected = True
        
        # Subscribe to all instruments
        tokens = list(self.token_to_symbol.keys())
        if tokens:
            self.subscribe_tokens(tokens)
    
    def _on_close(self, ws, code, reason) -> None:
        """Handle WebSocket disconnection"""
        logging.info(f"WebSocket disconnected: {reason} (Code: {code})")
        self.connected = False
        
        # Connection will auto-reconnect via KiteTicker
    
    def _on_error(self, ws, code, reason) -> None:
        """Handle WebSocket error"""
        logging.error(f"WebSocket error: {reason} (Code: {code})")
    
    def _price_processor_loop(self) -> None:
        """Background thread to process price updates and trigger checks"""
        while self.is_running:
            # Process price updates
            try:
                price_updates = self.price_queue.get(timeout=0.1)
                
                # Notify price update callback if set
                if self.on_price_update:
                    self.on_price_update(price_updates)
                
                self.price_queue.task_done()
            except queue.Empty:
                pass
                
            # Process trigger checks
            try:
                # We don't need the actual data from the queue, just a signal to check
                _ = self.trigger_check_queue.get_nowait()
                
                # Notify trigger check callback if set
                if self.on_potential_trigger:
                    price_data = self.price_cache.get_all()
                    self.on_potential_trigger(price_data)
                
                self.trigger_check_queue.task_done()
            except queue.Empty:
                pass
            
            # Prevent CPU spinning
            time.sleep(0.001)
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Get latest price for a symbol"""
        return self.price_cache.get(symbol)
    
    def get_all_prices(self) -> Dict[str, float]:
        """Get all latest prices"""
        return self.price_cache.get_all()