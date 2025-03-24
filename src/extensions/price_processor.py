# src/extensions/price_processor.py
"""
Python wrapper for the C++ price processor extension
Fallback to pure Python implementation if extension not available
"""
import logging
from typing import Dict, List, Tuple, Optional
import time

# Try to import the C++ extension
try:
    import price_processor as cpp_processor
    HAS_CPP_EXTENSION = True
    logging.info("Using C++ extension for price processing")
except ImportError:
    HAS_CPP_EXTENSION = False
    logging.warning("C++ extension not available, using pure Python implementation")

class PriceProcessor:
    """
    High-performance price processor for tick data
    Will use C++ extension if available, otherwise falls back to Python
    """
    
    def __init__(self, trigger_threshold: float = 0.99):
        self.trigger_threshold = trigger_threshold
        
        # Initialize the C++ processor if available
        if HAS_CPP_EXTENSION:
            cpp_processor.init_processor()
            cpp_processor.set_trigger_threshold(trigger_threshold)
        else:
            # Python fallback data structures
            self.last_prices = {}
            self.trade_types = {}
            self.target_prices = {}
            self.trigger_prices = {}
            self.gtt_prices = {}
    
    def update_price(self, symbol: str, price: float) -> None:
        """Update price for a single symbol"""
        if HAS_CPP_EXTENSION:
            cpp_processor.update_price(symbol, price)
        else:
            self.last_prices[symbol] = price
    
    def update_prices(self, price_dict: Dict[str, float]) -> None:
        """Update prices for multiple symbols at once"""
        if HAS_CPP_EXTENSION:
            symbols = list(price_dict.keys())
            prices = [price_dict[s] for s in symbols]
            cpp_processor.update_prices(symbols, prices)
        else:
            self.last_prices.update(price_dict)
    
    def set_symbol_data(self, symbol: str, trade_type: str, 
                       target_price: float, trigger_price: float, 
                       gtt_price: float) -> None:
        """Set trading data for a symbol"""
        if HAS_CPP_EXTENSION:
            cpp_processor.set_symbol_data(
                symbol, trade_type, target_price, trigger_price, gtt_price
            )
        else:
            self.trade_types[symbol] = trade_type
            self.target_prices[symbol] = target_price
            self.trigger_prices[symbol] = trigger_price
            self.gtt_prices[symbol] = gtt_price
    
    def find_potential_triggers(self) -> List[Tuple[str, float]]:
        """Find symbols that are close to triggering"""
        if HAS_CPP_EXTENSION:
            return cpp_processor.find_potential_triggers()
        else:
            candidates = []
            
            for symbol, price in self.last_prices.items():
                # Skip symbols without required data
                if (symbol not in self.trade_types or 
                    symbol not in self.gtt_prices):
                    continue
                
                trade_type = self.trade_types[symbol]
                gtt_price = self.gtt_prices[symbol]
                
                # Check if price is close to trigger
                if trade_type == "SHORT" and price >= gtt_price * self.trigger_threshold:
                    candidates.append((symbol, price))
                elif trade_type == "LONG" and price <= gtt_price / self.trigger_threshold:
                    candidates.append((symbol, price))
            
            return candidates
    
    def check_triggers(self) -> List[Tuple[str, float]]:
        """Check for symbols that have triggered"""
        if HAS_CPP_EXTENSION:
            return cpp_processor.check_triggers()
        else:
            triggered = []
            
            for symbol, price in self.last_prices.items():
                # Skip symbols without required data
                if (symbol not in self.trade_types or 
                    symbol not in self.gtt_prices):
                    continue
                
                trade_type = self.trade_types[symbol]
                gtt_price = self.gtt_prices[symbol]
                
                # Check if trigger condition is met
                if trade_type == "SHORT" and price >= gtt_price:
                    triggered.append((symbol, price))
                elif trade_type == "LONG" and price <= gtt_price:
                    triggered.append((symbol, price))
            
            return triggered
    
    def __del__(self):
        """Clean up resources"""
        if HAS_CPP_EXTENSION:
            cpp_processor.cleanup()