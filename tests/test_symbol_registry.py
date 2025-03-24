# tests/test_symbol_registry.py
import unittest
import sys
import os
from datetime import datetime, timedelta

# Add the src directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.symbol_registry import SymbolRegistry, SymbolData

class TestSymbolRegistry(unittest.TestCase):
    """Test cases for the SymbolRegistry class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.registry = SymbolRegistry()
        
        # Create some test symbol data
        self.test_symbol1 = SymbolData(
            symbol="RELIANCE",
            token=256265,
            trade_type="LONG",
            buffer=2.5,
            exchange="NSE",
            product_type="CNC",
            quantity=1,
            timeframe="DAILY",
            current_price=2500.0,
            previous_close=2450.0,
            target_price=2388.75,
            trigger_price=2398.75,
            gtt_price=2393.75,
            validity_date="31-12-2025"
        )
        
        self.test_symbol2 = SymbolData(
            symbol="INFY",
            token=408065,
            trade_type="SHORT",
            buffer=3.0,
            exchange="NSE",
            product_type="MIS",
            quantity=10,
            timeframe="INTRADAY",
            current_price=1500.0,
            previous_close=1520.0,
            target_price=1565.6,
            trigger_price=1558.0,
            gtt_price=1562.0,
            validity_date="31-12-2025"
        )
        
        # Add the test symbols to the registry
        self.registry.add(self.test_symbol1)
        self.registry.add(self.test_symbol2)
    
    def test_get_by_symbol(self):
        """Test retrieving symbols by name"""
        # Test case-sensitive lookup
        symbol_data = self.registry.get_by_symbol("RELIANCE")
        self.assertIsNotNone(symbol_data)
        self.assertEqual(symbol_data.symbol, "RELIANCE")
        self.assertEqual(symbol_data.token, 256265)
        
        # Test case-insensitive lookup
        symbol_data = self.registry.get_by_symbol("reliance", case_sensitive=False)
        self.assertIsNotNone(symbol_data)
        self.assertEqual(symbol_data.symbol, "RELIANCE")
        
        # Test non-existent symbol
        symbol_data = self.registry.get_by_symbol("NON_EXISTENT")
        self.assertIsNone(symbol_data)
    
    def test_get_by_token(self):
        """Test retrieving symbols by instrument token"""
        symbol_data = self.registry.get_by_token(256265)
        self.assertIsNotNone(symbol_data)
        self.assertEqual(symbol_data.symbol, "RELIANCE")
        
        # Test non-existent token
        symbol_data = self.registry.get_by_token(999999)
        self.assertIsNone(symbol_data)
    
    def test_update_price(self):
        """Test updating price for a symbol"""
        new_price = 2550.0
        self.registry.update_price("RELIANCE", new_price)
        
        # Check if price was updated
        symbol_data = self.registry.get_by_symbol("RELIANCE")
        self.assertEqual(symbol_data.current_price, new_price)
    
    def test_update_prices_batch(self):
        """Test updating prices for multiple symbols at once"""
        price_updates = {
            "RELIANCE": 2600.0,
            "INFY": 1550.0
        }
        self.registry.update_prices_batch(price_updates)
        
        # Check if prices were updated
        symbol_data1 = self.registry.get_by_symbol("RELIANCE")
        symbol_data2 = self.registry.get_by_symbol("INFY")
        
        self.assertEqual(symbol_data1.current_price, 2600.0)
        self.assertEqual(symbol_data2.current_price, 1550.0)
    
    def test_get_active_symbols(self):
        """Test getting list of active symbols"""
        active_symbols = self.registry.get_active_symbols()
        self.assertEqual(len(active_symbols), 2)
        self.assertIn("RELIANCE", active_symbols)
        self.assertIn("INFY", active_symbols)
        
        # Add a GTT order ID to make one symbol inactive
        self.test_symbol1.gtt_order_id = 12345
        self.test_symbol1.gtt_status = "Active"
        
        # Re-add the updated symbol
        self.registry.add(self.test_symbol1)
        
        # Check that only one symbol is now active
        active_symbols = self.registry.get_active_symbols()
        self.assertEqual(len(active_symbols), 1)
        self.assertIn("INFY", active_symbols)
    
    def test_get_all_tokens(self):
        """Test getting all instrument tokens"""
        tokens = self.registry.get_all_tokens()
        self.assertEqual(len(tokens), 2)
        self.assertIn(256265, tokens)
        self.assertIn(408065, tokens)
    
    def test_get_potential_triggers(self):
        """Test finding potential trigger conditions"""
        # Set price just below trigger for SHORT
        self.registry.update_price("INFY", 1556.0)  # Just below trigger price of 1558.0
        
        # No triggers yet
        triggers = self.registry.get_potential_triggers()
        self.assertEqual(len(triggers), 0)
        
        # Set price at trigger threshold
        threshold_price = 1558.0 * 0.99  # 99% of trigger price
        self.registry.update_price("INFY", threshold_price)
        
        # Should have potential trigger
        triggers = self.registry.get_potential_triggers()
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0][0], "INFY")
        
        # Set price just above trigger for LONG
        self.registry.update_price("RELIANCE", 2400.0)  # Just above trigger price of 2398.75
        
        # No additional triggers yet
        triggers = self.registry.get_potential_triggers()
        self.assertEqual(len(triggers), 1)
        
        # Set price at trigger threshold
        threshold_price = 2398.75 / 0.99  # Trigger price / 99%
        self.registry.update_price("RELIANCE", threshold_price)
        
        # Should have both potential triggers
        triggers = self.registry.get_potential_triggers()
        self.assertEqual(len(triggers), 2)

if __name__ == "__main__":
    unittest.main()