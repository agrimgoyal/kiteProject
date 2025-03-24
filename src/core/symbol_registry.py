# src/core/symbol_registry.py
import threading
import numpy as np
from datetime import datetime
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Set, Any, Tuple, Union

@dataclass
class SymbolData:
    """Optimized container for symbol data"""
    symbol: str
    token: int 
    trade_type: str
    buffer: float
    exchange: str
    product_type: str = "CNC"
    quantity: int = 1
    timeframe: str = "DAILY"
    
    # Dynamic values
    current_price: float = 0.0
    previous_close: float = 0.0
    target_price: float = 0.0
    trigger_price: float = 0.0
    gtt_price: float = 0.0
    
    # Order tracking
    gtt_order_id: Optional[int] = None
    gtt_status: str = ""
    order_status: str = ""
    remaining_quantity: int = None
    signal_id: str = ""
    strategy: str = ""
    
    # Date fields
    validity_date: str = ""
    signal_date: str = ""
    order_date: str = ""
    
    # Pre-computed fields
    symbol_upper: str = field(init=False)
    validity_date_obj: datetime = field(default=None, init=False)
    
    def __post_init__(self):
        # Set derived values
        self.symbol_upper = self.symbol.upper()
        
        # Set default remaining quantity
        if self.remaining_quantity is None:
            self.remaining_quantity = self.quantity
        
        # Parse date objects
        if self.validity_date:
            try:
                self.validity_date_obj = datetime.strptime(self.validity_date, "%d-%m-%Y").date()
            except ValueError:
                logging.warning(f"Invalid validity date format for {self.symbol}: {self.validity_date}")
                self.validity_date_obj = None


class SymbolRegistry:
    """High-performance registry for symbol data"""
    
    def __init__(self):
        # Multiple indices for fast access patterns
        self._by_symbol = {}        # symbol -> SymbolData
        self._by_symbol_upper = {}  # uppercase symbol -> SymbolData
        self._by_token = {}         # token -> SymbolData
        self._by_signal_id = {}     # signal_id -> SymbolData
        self._by_gtt_id = {}        # gtt_id -> SymbolData
        
        # Fine-grained locks for different indices
        self._symbol_lock = threading.RLock()
        self._token_lock = threading.RLock()
        self._order_lock = threading.RLock()
        
        # Price data arrays for vectorized operations
        self._symbols: List[str] = []
        self._tokens: List[int] = []
        self._prices: np.ndarray = np.array([])
        self._trade_types: List[str] = []
        self._price_lock = threading.RLock()
    
    def add(self, symbol_data: SymbolData) -> None:
        """Add a symbol to the registry with multi-index"""
        with self._symbol_lock:
            symbol = symbol_data.symbol
            self._by_symbol[symbol] = symbol_data
            self._by_symbol_upper[symbol.upper()] = symbol_data
            
            # Add to arrays for vectorized operations
            if symbol not in self._symbols:
                self._symbols.append(symbol)
                self._trade_types.append(symbol_data.trade_type)
        
        with self._token_lock:
            if symbol_data.token:
                self._by_token[symbol_data.token] = symbol_data
                # Update token list
                if symbol_data.token not in self._tokens:
                    self._tokens.append(symbol_data.token)
        
        with self._order_lock:
            if symbol_data.signal_id:
                self._by_signal_id[symbol_data.signal_id] = symbol_data
                
            if symbol_data.gtt_order_id:
                self._by_gtt_id[symbol_data.gtt_order_id] = symbol_data
    
    def get_by_symbol(self, symbol: str, case_sensitive: bool = True) -> Optional[SymbolData]:
        """Get symbol data with case sensitivity option"""
        if case_sensitive:
            return self._by_symbol.get(symbol)
        return self._by_symbol_upper.get(symbol.upper())
    
    def get_by_token(self, token: int) -> Optional[SymbolData]:
        """Get symbol data by instrument token"""
        return self._by_token.get(token)
    
    def get_by_signal_id(self, signal_id: str) -> Optional[SymbolData]:
        """Get symbol data by signal ID"""
        return self._by_signal_id.get(signal_id)
    
    def get_by_gtt_id(self, gtt_id: int) -> Optional[SymbolData]:
        """Get symbol data by GTT order ID"""
        return self._by_gtt_id.get(gtt_id)
    
    def update_price(self, symbol: str, price: float) -> None:
        """Update price with minimal locking"""
        with self._price_lock:
            symbol_data = self._by_symbol.get(symbol)
            if symbol_data:
                symbol_data.current_price = price
    
    def update_prices_batch(self, price_dict: Dict[str, float]) -> None:
        """Update multiple prices at once with minimal locking"""
        with self._price_lock:
            for symbol, price in price_dict.items():
                symbol_data = self._by_symbol.get(symbol)
                if symbol_data:
                    symbol_data.current_price = price
    
    def get_active_symbols(self) -> List[str]:
        """Get list of symbols that need monitoring"""
        active_symbols = []
        
        with self._symbol_lock:
            for symbol, data in self._by_symbol.items():
                # Skip if has active GTT
                if data.gtt_order_id and data.gtt_status not in ["", "Expired", "Failed", "Executed/Expired"]:
                    continue
                    
                # Skip if not valid trading
                # This is a simplified check - full check would be in trading logic
                if data.validity_date_obj and datetime.now().date() > data.validity_date_obj:
                    continue
                    
                active_symbols.append(symbol)
                
        return active_symbols
    
    def get_all_tokens(self) -> List[int]:
        """Get list of all instrument tokens"""
        with self._token_lock:
            return list(self._tokens)
    
    def get_potential_triggers(self, price_threshold: float = 0.99) -> List[Tuple[str, float]]:
        """Find symbols that are close to triggering conditions"""
        candidates = []
        
        with self._price_lock:
            # This could be optimized with NumPy/Cython for larger datasets
            for symbol, data in self._by_symbol.items():
                # Skip if already has GTT order
                if data.gtt_order_id and data.gtt_status not in ["", "Expired", "Failed", "Executed/Expired"]:
                    continue
                
                current_price = data.current_price
                gtt_price = data.gtt_price
                
                if current_price <= 0 or gtt_price <= 0:
                    continue
                    
                trade_type = data.trade_type.upper()
                
                # Check if price is close to trigger
                if trade_type == "SHORT" and current_price >= gtt_price * price_threshold:
                    candidates.append((symbol, current_price))
                elif trade_type == "LONG" and current_price <= gtt_price / price_threshold:
                    candidates.append((symbol, current_price))
        
        return candidates