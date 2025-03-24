# src/core/engine.py
import logging
import threading
import time
import queue
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set, Callable
import os
import concurrent.futures
from dataclasses import dataclass

from .market_data import MarketDataHandler
from .order_manager import OrderManager
from .symbol_registry import SymbolRegistry, SymbolData
from ..utils.performance import PerformanceMonitor
from ..utils.io_manager import CSVManager

@dataclass
class TradingConfig:
    """Configuration for trading engine"""
    api_key: str
    api_secret: str
    access_token: str
    symbols_path: str
    update_interval: int
    test_mode: bool
    time_based_test_mode: bool
    gtt_expiry_time: str
    auto_test_start_time: str
    auto_test_end_time: str
    intraday_time: str
    trigger_threshold_adjustment: float
    max_orders_per_day: int
    order_alert_threshold: int
    use_buffer_percentage: bool
    move_expired_orders: bool
    expired_orders_file: str
    completed_orders_file: str
    cleanup_time: str
    last_trading_day: str
    delete_orders_on_shutdown: bool


class TradingEngine:
    """High-performance trading engine"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.is_running = False
        
        # Initialize core components
        self.registry = SymbolRegistry()
        self.order_manager = OrderManager(
            api_key=config.api_key,
            api_secret=config.api_secret,
            access_token=config.access_token,
            max_orders_per_day=config.max_orders_per_day,
            order_alert_threshold=config.order_alert_threshold,
            test_mode=config.test_mode
        )
        
        # Market data will be initialized after symbols are loaded
        self.market_data = None
        
        # CSV manager for efficient I/O
        self.csv_manager = CSVManager()
        
        # Thread management
        self.threads = {}
        
        # Event flags
        self.expiry_time_passed = False
        self.intraday_time_passed = False
        
        # Performance monitoring
        self.perf_monitor = PerformanceMonitor()
        
        # Task scheduling
        self.scheduled_tasks = queue.PriorityQueue()
        self.scheduler_thread = None
        
        # Symbol DataFrame - maintained for backward compatibility
        self.symbols_df = None
    
    def start(self) -> bool:
        """Start the trading engine"""
        if self.is_running:
            return True
            
        logging.info("Starting trading engine...")
        self.is_running = True
        
        # Apply auto test mode if configured
        self._apply_auto_test_mode()
        
        # Load symbols
        if not self._load_symbols():
            logging.error("Failed to load symbols, stopping")
            self.is_running = False
            return False
        
        # Calculate price targets
        self._calculate_price_targets()
        
        # Initialize market data after symbols are loaded
        token_to_symbol = {
            self.registry._by_symbol[s].token: s 
            for s in self.registry._by_symbol 
            if hasattr(self.registry._by_symbol[s], 'token') and self.registry._by_symbol[s].token
        }
        
        self.market_data = MarketDataHandler(
            api_key=self.config.api_key,
            access_token=self.config.access_token,
            token_to_symbol=token_to_symbol
        )
        
        # Set market data callbacks
        self.market_data.on_price_update = self._on_price_update
        self.market_data.on_potential_trigger = self._on_potential_trigger
        
        # Start components
        self.order_manager.start()
        self.market_data.start()
        
        # Start scheduler thread
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="Scheduler"
        )
        self.scheduler_thread.start()
        
        # Schedule periodic tasks
        self._schedule_periodic_tasks()
        
        logging.info(f"Trading engine started (Test Mode: {self.config.test_mode})")
        return True
    
    def stop(self) -> None:
        """Stop the trading engine"""
        if not self.is_running:
            return
            
        logging.info("Stopping trading engine...")
        self.is_running = False
        
        # Optionally delete all active GTT orders on shutdown
        if self.config.delete_orders_on_shutdown and not self.config.test_mode:
            logging.info("Deleting all active GTT orders on shutdown")
            self._delete_all_gtts()
        
        # Stop components
        if self.market_data:
            self.market_data.stop()
        
        if self.order_manager:
            self.order_manager.stop()
        
        # Wait for scheduler thread to finish
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=1.0)
        
        logging.info("Trading engine stopped")
    
    def _delete_all_gtts(self) -> None:
        """Delete all active GTT orders - used during shutdown"""
        if self.config.test_mode:
            return
            
        try:
            # Verify GTTs to get current list
            active_gtts = self.order_manager.verify_gtt_orders()
            
            # Delete each one
            for gtt_id in active_gtts:
                self.order_manager.delete_gtt_order(gtt_id)
                
            logging.info(f"Deleted {len(active_gtts)} GTT orders during shutdown")
        except Exception as e:
            logging.error(f"Error deleting GTT orders during shutdown: {e}")
    
    def _apply_auto_test_mode(self) -> None:
        """Apply auto test mode based on time if configured"""
        if self.config.time_based_test_mode:
            current_time = datetime.now().strftime("%H:%M:%S")
            if current_time >= self.config.auto_test_start_time or current_time <= self.config.auto_test_end_time:
                self.config.test_mode = True
                logging.info("Test mode on: auto test mode running")
    
    def _load_symbols(self) -> bool:
        """Load symbols from CSV file"""
        try:
            # Load CSV file
            df = pd.read_csv(self.config.symbols_path)
            self.symbols_df = df  # Keep reference for backward compatibility
            
            # Add required columns if they don't exist
            required_columns = ["Symbol", "buffer", "Trade Type"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                logging.error(f"Missing required columns in CSV: {missing_columns}")
                return False
            
            # Add tracking columns if they don't exist
            tracking_columns = {
                "Current Price": np.nan,
                "Previous Close": np.nan, 
                "Target Price": np.nan,
                "Trigger Price": np.nan,
                "GTT Order Price": np.nan,
                "Exchange": "",
                "Quantity": 1,  # Default quantity
                "Product Type": "",
                "GTT Order ID": np.nan,
                "GTT Status": "",
                "Last Updated": "",
                "Signal Date": "",
                "Validity Date": "",
                "Order Status": "",
                "Remaining Quantity": np.nan,
                "Order Date": ""
            }
            
            for col, default_value in tracking_columns.items():
                if col not in df.columns:
                    df[col] = default_value
            
            # If Signal Date is empty, set it to today's date
            today_str = datetime.now().strftime("%d-%m-%Y")
            df.loc[df["Signal Date"].isna() | (df["Signal Date"] == ""), "Signal Date"] = today_str
            
            # If Validity Date is empty, set it to today's date
            df.loc[df["Validity Date"].isna() | (df["Validity Date"] == ""), "Validity Date"] = today_str
            
            # Initialize Remaining Quantity to match Quantity
            df.loc[df["Remaining Quantity"].isna(), "Remaining Quantity"] = df["Quantity"]
            
            # Add unique identifiers if needed
            if "signal_id" not in df.columns:
                self._add_unique_identifiers(df)
            
            # Convert dataframe to symbol registry
            for _, row in df.iterrows():
                symbol_data = SymbolData(
                    symbol=row["Symbol"],
                    token=0,  # Will be updated when instruments are loaded
                    trade_type=row["Trade Type"],
                    buffer=row["buffer"],
                    exchange=row.get("Exchange", ""),
                    product_type=row.get("Product Type", "CNC"),
                    quantity=int(row.get("Quantity", 1)),
                    timeframe=row.get("Timeframe", "DAILY"),
                    current_price=row.get("Current Price", 0.0),
                    previous_close=row.get("Previous Close", 0.0),
                    target_price=row.get("Target Price", 0.0),
                    trigger_price=row.get("Trigger Price", 0.0),
                    gtt_price=row.get("GTT Order Price", 0.0),
                    gtt_order_id=row.get("GTT Order ID") if not pd.isna(row.get("GTT Order ID")) else None,
                    gtt_status=row.get("GTT Status", ""),
                    order_status=row.get("Order Status", ""),
                    remaining_quantity=int(row.get("Remaining Quantity", row.get("Quantity", 1))),
                    signal_id=row.get("signal_id", ""),
                    strategy=row.get("Strategy", ""),
                    validity_date=row.get("Validity Date", today_str),
                    signal_date=row.get("Signal Date", today_str),
                    order_date=row.get("Order Date", "")
                )
                self.registry.add(symbol_data)
            
            # Fetch instrument tokens for all symbols
            self._fetch_instrument_tokens()
            
            # Fetch previous close prices
            self._fetch_previous_close_prices()
            
            logging.info(f"Loaded {len(self.registry._by_symbol)} symbols for tracking")
            return True
            
        except Exception as e:
            logging.error(f"Error loading symbols: {e}", exc_info=True)
            return False
    
    def _add_unique_identifiers(self, df: pd.DataFrame) -> None:
        """Add unique identifiers to each row"""
        import hashlib
        
        # Create signal_id column
        df["signal_id"] = ""
        
        # Generate unique IDs for each row
        for idx, row in df.iterrows():
            # Create a unique ID combining multiple factors
            symbol = row["Symbol"]
            strategy = str(row.get("Strategy", ""))
            timeframe = str(row.get("Timeframe", ""))
            trade_type = str(row.get("Trade Type", ""))
            signal_date = str(row.get("Signal Date", ""))
            quantity = str(row.get("Quantity", ""))
            
            # Include the index to ensure uniqueness for completely identical rows
            unique_id = f"{symbol}_{strategy}_{timeframe}_{trade_type}_{signal_date}_{quantity}_{idx}"
            
            # Generate a hash to make it shorter but still unique
            hash_id = hashlib.md5(unique_id.encode()).hexdigest()[:10]
            df.at[idx, "signal_id"] = hash_id
    
    def _fetch_instrument_tokens(self) -> None:
        """Fetch instrument tokens for all symbols"""
        try:
            logging.info("Fetching instrument tokens...")
            
            # Get all instruments from Kite
            instruments = self.order_manager.kite.instruments()
            
            # Create lookup dictionary
            instrument_lookup = {row["tradingsymbol"]: row for row in instruments}
            
            # Update tokens in registry
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = []
                
                for symbol, data in self.registry._by_symbol.items():
                    futures.append(executor.submit(self._update_symbol_token, symbol, data, instrument_lookup))
                
                # Wait for all to complete
                concurrent.futures.wait(futures)
            
            logging.info(f"Updated instrument tokens for {len(self.registry._by_token)} symbols")
            
        except Exception as e:
            logging.error(f"Error fetching instrument tokens: {e}", exc_info=True)
    
    def _update_symbol_token(self, symbol: str, data: SymbolData, instrument_lookup: Dict[str, Any]) -> None:
        """Update token and exchange for a symbol"""
        try:
            # Try direct match first (faster)
            if symbol in instrument_lookup:
                instrument = instrument_lookup[symbol]
                data.token = instrument["instrument_token"]
                data.exchange = instrument["exchange"]
                return
            
            # Try case-insensitive match
            symbol_upper = symbol.upper()
            for key, instrument in instrument_lookup.items():
                if key.upper() == symbol_upper:
                    data.token = instrument["instrument_token"]
                    data.exchange = instrument["exchange"]
                    return
                    
            logging.warning(f"No instrument token found for symbol: {symbol}")
            
        except Exception as e:
            logging.error(f"Error updating token for {symbol}: {e}")
    
    def _fetch_previous_close_prices(self) -> None:
        """Fetch the previous day's closing prices for all symbols"""
        try:
            logging.info("Fetching previous close prices...")
            
            # Get symbols with tokens
            symbols_with_tokens = [
                (s, data.token, data.exchange) 
                for s, data in self.registry._by_symbol.items() 
                if hasattr(data, 'token') and data.token
            ]
            
            # Process in chunks to avoid API limits
            chunk_size = 100
            chunks = [symbols_with_tokens[i:i + chunk_size] for i in range(0, len(symbols_with_tokens), chunk_size)]
            
            for chunk in chunks:
                try:
                    # Create instrument strings for API call
                    instruments = [f"{exchange}:{symbol}" for symbol, _, exchange in chunk]
                    
                    # Fetch quotes
                    quotes = self.order_manager.kite.quote(instruments)
                    
                    # Update previous close prices in registry
                    for symbol, token, exchange in chunk:
                        instrument_key = f"{exchange}:{symbol}"
                        if instrument_key in quotes:
                            close_price = quotes[instrument_key]['ohlc']['close']
                            
                            # Update in registry
                            symbol_data = self.registry.get_by_symbol(symbol)
                            if symbol_data:
                                symbol_data.previous_close = close_price
                                
                                # Also update DataFrame for backward compatibility
                                self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Previous Close"] = close_price
                    
                    # Be nice to the API
                    time.sleep(0.2)
                    
                except Exception as chunk_error:
                    logging.error(f"Error fetching quotes for chunk: {chunk_error}")
            
            logging.info("Previous close prices fetched")
            
        except Exception as e:
            logging.error(f"Error fetching previous close prices: {e}", exc_info=True)
    
    def _calculate_price_targets(self) -> None:
        """Calculate target and trigger prices based on previous close"""
        try:
            # Get all symbols with previous close prices
            symbols_data = [
                (symbol, data) 
                for symbol, data in self.registry._by_symbol.items() 
                if data.previous_close > 0
            ]
            
            for symbol, data in symbols_data:
                prev_close = data.previous_close
                buffer_value = data.buffer
                trade_type = data.trade_type.upper()
                
                # Use configuration for adjustments
                trigger_adj = self.config.trigger_threshold_adjustment
                gtt_place_diff = 0  # Default, can be made configurable
                
                if self.config.use_buffer_percentage:
                    if trade_type == "SHORT":
                        # For short positions
                        data.target_price = prev_close * (1 + buffer_value/100)
                        data.trigger_price = prev_close * (1 + (buffer_value - trigger_adj)/100)
                        data.gtt_price = prev_close * (1 + (buffer_value - gtt_place_diff)/100)
                    else:
                        # For long positions
                        data.target_price = prev_close * (1 - buffer_value/100)
                        data.trigger_price = prev_close * (1 - (buffer_value - trigger_adj)/100)
                        data.gtt_price = prev_close * (1 - (buffer_value - gtt_place_diff)/100)
                else:
                    # Use direct price mode (not percentage)
                    # This would be implemented based on specific requirements
                    if hasattr(data, 'entry_price') and data.entry_price > 0:
                        if trade_type == "SHORT":
                            data.target_price = data.entry_price
                            pct_diff = ((data.target_price / prev_close) - 1) * 100
                            data.trigger_price = prev_close * (1 + (pct_diff - trigger_adj)/100)
                            data.gtt_price = prev_close * (1 + (pct_diff - gtt_place_diff)/100)
                        else:
                            data.target_price = data.entry_price
                            pct_diff = ((prev_close / data.target_price) - 1) * 100
                            data.trigger_price = prev_close * (1 - (pct_diff - trigger_adj)/100)
                            data.gtt_price = prev_close * (1 - (pct_diff - gtt_place_diff)/100)
                
                # Apply tick size rounding if needed
                data.target_price = self._round_tick_price(prev_close, data.target_price)
                data.trigger_price = self._round_tick_price(prev_close, data.trigger_price)
                data.gtt_price = self._round_tick_price(prev_close, data.gtt_price)
                
                # Update DataFrame for backward compatibility
                self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Target Price"] = data.target_price
                self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Trigger Price"] = data.trigger_price
                self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Order Price"] = data.gtt_price
            
            logging.info(f"Calculated price targets for {len(symbols_data)} symbols")
            
        except Exception as e:
            logging.error(f"Error calculating price targets: {e}", exc_info=True)
    
    def _round_tick_price(self, prev_close: float, price: float) -> float:
        """Round price to tick size"""
        if prev_close <= 800:
            return round(price/0.05) * 0.05
        else:
            return round(price/0.1) * 0.1
    
    def _on_price_update(self, price_updates: Dict[str, float]) -> None:
        """Handle price updates from market data"""
        try:
            # Update prices in registry
            self.registry.update_prices_batch(price_updates)
            
            # Update DataFrame for backward compatibility
            for symbol, price in price_updates.items():
                self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Current Price"] = price
                self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Last Updated"] = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            logging.error(f"Error processing price updates: {e}")
    
    def _on_potential_trigger(self, price_data: Dict[str, float]) -> None:
        """Handle potential trigger events"""
        try:
            # Skip if expiry time has passed
            if self.expiry_time_passed:
                return
                
            # Get potential triggers
            candidates = self.registry.get_potential_triggers(price_threshold=0.99)
            
            if not candidates:
                return
                
            logging.info(f"Checking {len(candidates)} potential triggers")
            
            # Process each potential trigger
            for symbol, current_price in candidates:
                # Get symbol data
                data = self.registry.get_by_symbol(symbol)
                
                if not data:
                    continue
                
                # Skip if not valid for trading
                if not self._is_valid_for_trading(data):
                    continue
                
                # Check if trigger condition is met
                trade_type = data.trade_type.upper()
                trigger_met = False
                
                if trade_type == "SHORT" and current_price >= data.gtt_price:
                    trigger_met = True
                elif trade_type == "LONG" and current_price <= data.gtt_price:
                    trigger_met = True
                
                if trigger_met:
                    logging.info(f"Trigger condition met for {symbol}: Current {current_price}, GTT Price {data.gtt_price}")
                    
                    # Check if order already exists
                    if data.gtt_order_id and data.gtt_status not in ["", "Expired", "Failed", "Executed/Expired"]:
                        logging.info(f"Skipping {symbol} - Already has active order with status: {data.gtt_status}")
                        continue
                    
                    # Place GTT order
                    self._place_gtt_for_symbol(symbol, data)
        except Exception as e:
            logging.error(f"Error checking triggers: {e}")
    
    def _is_valid_for_trading(self, data: SymbolData) -> bool:
        """Check if a symbol is valid for trading based on timeframe and validity date"""
        try:
            # Check date validity
            today = datetime.now().date()
            
            if not data.validity_date_obj:
                # If no validity date, not valid
                return False
                
            # Check if the validity date has passed
            if today > data.validity_date_obj:
                return False
            
            # Get timeframe (default to Daily if not specified)
            timeframe = data.timeframe.upper() if data.timeframe else "DAILY"
            
            # Get current time
            now = datetime.now().time()
            
            # Parse expiry times
            intraday_time = datetime.strptime(self.config.intraday_time, "%H:%M:%S").time()
            gtt_expiry_time = datetime.strptime(self.config.gtt_expiry_time, "%H:%M:%S").time()
            
            # Check validity based on timeframe
            if timeframe == "INTRADAY":
                # Only valid if today is the validity date and we haven't passed intraday_time
                return ((today == data.validity_date_obj and now < intraday_time and not self.intraday_time_passed) or 
                        (today < data.validity_date_obj))
            elif timeframe == "DAILY":
                # Only valid on the validity date and before gtt_expiry_time
                return ((today == data.validity_date_obj and now < gtt_expiry_time and not self.expiry_time_passed) or 
                        (today < data.validity_date_obj))
            elif timeframe in ["WEEKLY", "MONTHLY"]:
                # Valid until the validity date (inclusive) and before gtt_expiry_time
                return ((today == data.validity_date_obj and now < gtt_expiry_time and not self.expiry_time_passed) or 
                        (today < data.validity_date_obj))
            else:
                # Unknown timeframe - default to daily rules
                logging.warning(f"Unknown timeframe '{timeframe}' for {data.symbol}. Using Daily rules.")
                return (today == data.validity_date_obj and now < gtt_expiry_time and not self.expiry_time_passed)
        
        except Exception as e:
            logging.error(f"Error checking validity for {data.symbol}: {e}")
            return False
    
    def _place_gtt_for_symbol(self, symbol: str, data: SymbolData) -> None:
        """Place a GTT order for a symbol"""
        try:
            # Prepare unique tag
            unique_tag = self._get_unique_order_tag(symbol, data.signal_id)
            
            # Place the appropriate order based on timeframe
            if data.timeframe.upper() == "INTRADAY":
                # For intraday orders, implementation would go here
                pass
            else:
                # Place GTT for non-intraday
                if ((data.trade_type.upper() == "SHORT" and data.current_price < data.trigger_price) or 
                    (data.trade_type.upper() == "LONG" and data.current_price > data.trigger_price)):
                    # Place GTT if price is outside trigger range
                    gtt_id = self.order_manager.place_gtt_order(
                        symbol=symbol,
                        exchange=data.exchange,
                        trigger_price=data.trigger_price,
                        target_price=data.target_price,
                        trade_type=data.trade_type,
                        quantity=data.quantity,
                        product_type=data.product_type,
                        signal_id=data.signal_id,
                        unique_tag=unique_tag
                    )
                    
                    if gtt_id:
                        # Update registry and DataFrame
                        data.gtt_order_id = gtt_id
                        data.gtt_status = "Test Placed" if self.config.test_mode else "Active"
                        
                        # Update DataFrame for backward compatibility
                        self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Order ID"] = gtt_id
                        self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Status"] = data.gtt_status
                        
                        logging.info(f"GTT order placed for {symbol}. ID: {gtt_id}")
                    elif not self.config.test_mode:
                        data.gtt_status = "Failed"
                        self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Status"] = "Failed"
                        logging.error(f"Failed to place GTT order for {symbol}")
                    else:
                        data.gtt_status = "Would place (test mode)"
                        data.gtt_order_id = -1
                        self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Status"] = "Would place (test mode)"
                        self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Order ID"] = -1
                else:
                    # Price already beyond trigger - would place direct order here
                    pass
        except Exception as e:
            logging.error(f"Error placing order for {symbol}: {e}")
    
    def _get_unique_order_tag(self, symbol: str, signal_id: str) -> str:
        """Generate a unique tag for orders to identify them"""
        # Max length is 20 chars for Kite tags
        timestamp = datetime.now().strftime("%y%m%d%H%M")
        
        # Use signal_id for uniqueness
        tag = f"scr_{signal_id[:5]}_{timestamp}"
        
        # Ensure tag doesn't exceed Kite's 20 char limit
        if len(tag) > 20:
            tag = tag[:20]
            
        return tag
    
    def _scheduler_loop(self) -> None:
        """Main scheduler loop for periodic tasks"""
        while self.is_running:
            try:
                # Check if there are tasks to run
                now = time.time()
                
                while not self.scheduled_tasks.empty():
                    # Peek at the next task
                    next_run, task_id, task_func, task_args = self.scheduled_tasks.queue[0]
                    
                    if next_run <= now:
                        # Task is due, remove it from the queue
                        self.scheduled_tasks.get_nowait()
                        
                        # Run the task in a separate thread to avoid blocking the scheduler
                        threading.Thread(
                            target=self._run_task,
                            args=(task_id, task_func, task_args),
                            daemon=True
                        ).start()
                        
                        # If the task is periodic, reschedule it
                        if task_id.startswith("periodic_"):
                            interval = task_args.get("interval", 60)
                            self._schedule_task(task_id, task_func, task_args, interval)
                    else:
                        # No more due tasks
                        break
                        
                # Sleep to prevent CPU spinning
                time.sleep(0.1)
                
            except Exception as e:
                logging.error(f"Error in scheduler loop: {e}")
                time.sleep(1.0)
    
    def _run_task(self, task_id: str, task_func: Callable, task_args: Dict[str, Any]) -> None:
        """Run a scheduled task with proper error handling"""
        try:
            task_func(**task_args)
        except Exception as e:
            logging.error(f"Error running task {task_id}: {e}")
    
    def _schedule_task(self, task_id: str, task_func: Callable, task_args: Dict[str, Any], delay: float) -> None:
        """Schedule a task to run after a delay"""
        next_run = time.time() + delay
        self.scheduled_tasks.put((next_run, task_id, task_func, task_args))
    
    def _schedule_periodic_tasks(self) -> None:
        """Schedule all periodic tasks"""
        # Save CSV every 5 minutes
        self._schedule_task(
            "periodic_save_csv",
            self._save_csv,
            {},
            300  # 5 minutes
        )
        
        # Verify GTT orders every 15 minutes
        self._schedule_task(
            "periodic_verify_gtts",
            self._verify_gtt_orders,
            {},
            900  # 15 minutes
        )
        
        # Check for partially executed orders every 30 seconds
        self._schedule_task(
            "periodic_check_partial_orders",
            self._check_partially_executed_orders,
            {},
            30  # 30 seconds
        )
        
        # Schedule GTT cancellation task at expiry time
        self._schedule_gtt_cancellation_tasks()
        
        # Schedule cleanup at designated time
        self._schedule_cleanup_task()
    
    def _schedule_gtt_cancellation_tasks(self) -> None:
        """Schedule GTT cancellation at expiry times"""
        now = datetime.now()
        
        # Parse expiry times
        intraday_time = datetime.strptime(self.config.intraday_time, "%H:%M:%S").time()
        intraday_dt = datetime.combine(now.date(), intraday_time)
        
        gtt_expiry_time = datetime.strptime(self.config.gtt_expiry_time, "%H:%M:%S").time()
        expiry_dt = datetime.combine(now.date(), gtt_expiry_time)
        
        # If times have already passed for today, schedule for tomorrow
        if now.time() >= intraday_time:
            intraday_dt += timedelta(days=1)
            
        if now.time() >= gtt_expiry_time:
            expiry_dt += timedelta(days=1)
        
        # Calculate delays
        intraday_delay = (intraday_dt - now).total_seconds()
        expiry_delay = (expiry_dt - now).total_seconds()
        
        # Schedule intraday cancellation
        self._schedule_task(
            "cancel_intraday_orders",
            self._cancel_intraday_orders,
            {},
            intraday_delay
        )
        
        # Schedule normal GTT cancellation
        self._schedule_task(
            "cancel_gtt_orders",
            self._cancel_gtt_orders,
            {},
            expiry_delay
        )
        
        logging.info(f"Scheduled GTT cancellation tasks. Intraday at: {intraday_time}, Regular at: {gtt_expiry_time}")
    
    def _schedule_cleanup_task(self) -> None:
        """Schedule daily cleanup task"""
        now = datetime.now()
        
        # Parse cleanup time
        cleanup_time = datetime.strptime(self.config.cleanup_time, "%H:%M:%S").time()
        cleanup_dt = datetime.combine(now.date(), cleanup_time)
        
        # If time has already passed for today, schedule for tomorrow
        if now.time() >= cleanup_time:
            cleanup_dt += timedelta(days=1)
            
        # Calculate delay
        cleanup_delay = (cleanup_dt - now).total_seconds()
        
        # Schedule cleanup
        self._schedule_task(
            "daily_cleanup",
            self._cleanup_expired_orders,
            {},
            cleanup_delay
        )
        
        logging.info(f"Scheduled daily cleanup task at: {cleanup_time}")
    
    def _cancel_intraday_orders(self) -> None:
        """Cancel all intraday orders at intraday expiry time"""
        logging.info("Cancelling intraday orders at expiry time")
        self.intraday_time_passed = True
        
        if self.config.test_mode:
            logging.info("TEST MODE: Would cancel intraday orders")
            return
            
        try:
            # Get all intraday symbols
            intraday_symbols = []
            
            for symbol, data in self.registry._by_symbol.items():
                if data.timeframe.upper() == "INTRADAY" and data.gtt_order_id and data.gtt_status not in ["", "Expired", "Cancelled", "Failed"]:
                    intraday_symbols.append((symbol, data))
            
            logging.info(f"Found {len(intraday_symbols)} intraday orders to cancel")
            
            # Cancel each order
            for symbol, data in intraday_symbols:
                gtt_id = data.gtt_order_id
                if gtt_id in [-1, -2]:  # Skip test orders
                    continue
                    
                success = self.order_manager.delete_gtt_order(gtt_id)
                
                if success:
                    data.gtt_status = "Expired (Intraday)"
                    data.gtt_order_id = None
                    
                    # Update DataFrame for backward compatibility
                    self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Status"] = "Expired (Intraday)"
                    self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Order ID"] = np.nan
                else:
                    logging.warning(f"Failed to cancel intraday GTT order {gtt_id} for {symbol}")
            
            # Save changes
            self._save_csv()
            
            # Reset flag for next day at midnight
            self._schedule_task(
                "reset_intraday_flag",
                self._reset_intraday_flag,
                {},
                self._seconds_until_midnight()
            )
            
        except Exception as e:
            logging.error(f"Error cancelling intraday orders: {e}")
    
    def _cancel_gtt_orders(self) -> None:
        """Cancel all GTT orders at expiry time"""
        logging.info("Cancelling all GTT orders at expiry time")
        self.expiry_time_passed = True
        
        if self.config.test_mode:
            logging.info("TEST MODE: Would cancel all GTT orders")
            return
            
        try:
            # Get all valid GTT orders
            gtt_orders = []
            
            for symbol, data in self.registry._by_symbol.items():
                # Only consider GTTs for symbols with today's validity date
                if (data.validity_date_obj == datetime.now().date() and 
                    data.gtt_order_id and 
                    data.gtt_status not in ["", "Expired", "Cancelled", "Failed"]):
                    gtt_orders.append((symbol, data))
            
            logging.info(f"Found {len(gtt_orders)} GTT orders to cancel at expiry")
            
            # Cancel each order
            for symbol, data in gtt_orders:
                gtt_id = data.gtt_order_id
                if gtt_id in [-1, -2]:  # Skip test orders
                    continue
                    
                success = self.order_manager.delete_gtt_order(gtt_id)
                
                if success:
                    data.gtt_status = "Expired"
                    data.gtt_order_id = None
                    
                    # Update DataFrame for backward compatibility
                    self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Status"] = "Expired"
                    self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Order ID"] = np.nan
                else:
                    logging.warning(f"Failed to cancel GTT order {gtt_id} for {symbol}")
            
            # Save changes
            self._save_csv()
            
            # Reset flag for next day at midnight
            self._schedule_task(
                "reset_expiry_flag",
                self._reset_expiry_flag,
                {},
                self._seconds_until_midnight()
            )
            
        except Exception as e:
            logging.error(f"Error cancelling GTT orders: {e}")
    
    def _reset_intraday_flag(self) -> None:
        """Reset the intraday time passed flag at midnight"""
        self.intraday_time_passed = False
        logging.info("Reset intraday flag for new day")
    
    def _reset_expiry_flag(self) -> None:
        """Reset the expiry time passed flag at midnight"""
        self.expiry_time_passed = False
        logging.info("Reset expiry flag for new day")
    
    def _seconds_until_midnight(self) -> float:
        """Calculate seconds until midnight for scheduling resets"""
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return (tomorrow - now).total_seconds()
    
    def _cleanup_expired_orders(self) -> None:
        """Move expired orders to a separate CSV file"""
        if not self.config.move_expired_orders:
            logging.info("Skipping expired orders cleanup - feature disabled")
            return
            
        try:
            logging.info("Running scheduled cleanup operations")
            today = datetime.now().date()
            
            # Find expired rows
            expired_rows = []
            symbols_to_remove = []
            
            for symbol, data in self.registry._by_symbol.items():
                # Check if validity date is past
                if data.validity_date_obj and data.validity_date_obj < today:
                    # Add symbol data to expired list
                    expired_row = {attr: getattr(data, attr) for attr in dir(data) if not attr.startswith('_') and not callable(getattr(data, attr))}
                    expired_row["Expiry Date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    expired_rows.append(expired_row)
                    
                    # Mark for removal
                    symbols_to_remove.append(symbol)
                
            # If we have expired rows, save them to file
            if expired_rows:
                # Convert to DataFrame
                expired_df = pd.DataFrame(expired_rows)
                
                # Save to expired orders file
                if os.path.exists(self.config.expired_orders_file):
                    # Append to existing file
                    existing_expired = pd.read_csv(self.config.expired_orders_file)
                    combined_expired = pd.concat([existing_expired, expired_df], ignore_index=True)
                    combined_expired.to_csv(self.config.expired_orders_file, index=False)
                else:
                    # Create new file
                    expired_df.to_csv(self.config.expired_orders_file, index=False)
                
                # Remove expired symbols from registry
                for symbol in symbols_to_remove:
                    # Remove from DataFrame for backward compatibility
                    self.symbols_df = self.symbols_df[self.symbols_df["Symbol"] != symbol]
                
                # Save the updated main DataFrame
                self._save_csv()
                
                logging.info(f"Moved {len(expired_rows)} expired orders to {self.config.expired_orders_file}")
            else:
                logging.info("No expired orders to clean up")
                
        except Exception as e:
            logging.error(f"Error during expired orders cleanup: {e}")
    
    def _check_partially_executed_orders(self) -> None:
        """Check for partially executed orders and place follow-up orders"""
        # Implementation would go here
        pass
    
    def _verify_gtt_orders(self) -> None:
        """Verify the status of all GTT orders"""
        if self.config.test_mode:
            return
            
        try:
            # Get current GTT orders from Kite
            active_orders = self.order_manager.verify_gtt_orders()
            
            # Update registry with current status
            for symbol, data in self.registry._by_symbol.items():
                gtt_id = data.gtt_order_id
                
                # Skip invalid GTT IDs
                if not gtt_id or gtt_id in [-1, -2]:
                    continue
                    
                # Check if order still exists
                if gtt_id in active_orders:
                    status = active_orders[gtt_id].get("status", "Unknown")
                    
                    # Update in registry
                    data.gtt_status = status
                    
                    # Update DataFrame for backward compatibility
                    self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Status"] = status
                else:
                    # Order no longer exists
                    data.gtt_status = "Executed/Expired"
                    data.gtt_order_id = None
                    
                    # Update DataFrame for backward compatibility
                    self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Status"] = "Executed/Expired"
                    self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Order ID"] = np.nan
                    
                    logging.info(f"GTT order for {symbol} is no longer active (possibly executed)")
            
            # Save the updated data
            self._save_csv()
                
        except Exception as e:
            logging.error(f"Error verifying GTT orders: {e}")
    
    def _save_csv(self) -> None:
        """Save the DataFrame to a CSV file"""
        try:
            # Save DataFrame to CSV
            self.symbols_df.to_csv(self.config.symbols_path, index=False)
            logging.debug(f"Saved data to {self.config.symbols_path}")
        except Exception as e:
            logging.error(f"Error saving CSV file: {e}")