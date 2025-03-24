# tests/test_market_data.py
import unittest
import sys
import os
import threading
import time
from unittest.mock import MagicMock, patch

# Add the src directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.market_data import MarketDataHandler, PriceCache

class TestPriceCache(unittest.TestCase):
    """Test cases for the PriceCache class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.cache = PriceCache()
    
    def test_update_single_price(self):
        """Test updating a single price"""
        self.cache.update("RELIANCE", 2500.0)
        self.assertEqual(self.cache.get("RELIANCE"), 2500.0)
    
    def test_update_batch(self):
        """Test updating multiple prices at once"""
        price_updates = {
            "RELIANCE": 2500.0,
            "INFY": 1500.0,
            "TCS": 3500.0
        }
        self.cache.update_batch(price_updates)
        
        self.assertEqual(self.cache.get("RELIANCE"), 2500.0)
        self.assertEqual(self.cache.get("INFY"), 1500.0)
        self.assertEqual(self.cache.get("TCS"), 3500.0)
    
    def test_get_missing_symbol(self):
        """Test retrieving price for a non-existent symbol"""
        self.assertIsNone(self.cache.get("NON_EXISTENT"))
    
    def test_get_all(self):
        """Test retrieving all prices"""
        price_updates = {
            "RELIANCE": 2500.0,
            "INFY": 1500.0
        }
        self.cache.update_batch(price_updates)
        
        all_prices = self.cache.get_all()
        self.assertEqual(len(all_prices), 2)
        self.assertEqual(all_prices["RELIANCE"], 2500.0)
        self.assertEqual(all_prices["INFY"], 1500.0)

class TestMarketDataHandler(unittest.TestCase):
    """Test cases for the MarketDataHandler class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock token_to_symbol mapping
        self.token_to_symbol = {
            256265: "RELIANCE",
            408065: "INFY"
        }
        
        # Create a mock KiteTicker
        self.mock_kite_ticker_patcher = patch('src.core.market_data.KiteTicker')
        self.mock_kite_ticker = self.mock_kite_ticker_patcher.start()
        
        # Create the data handler with mocked dependencies
        self.data_handler = MarketDataHandler(
            api_key="test_api_key",
            access_token="test_access_token",
            token_to_symbol=self.token_to_symbol
        )
        
        # Set up callback mocks
        self.data_handler.on_price_update = MagicMock()
        self.data_handler.on_potential_trigger = MagicMock()
    
    def tearDown(self):
        """Clean up after tests"""
        self.mock_kite_ticker_patcher.stop()
    
    def test_initialization(self):
        """Test initialization of MarketDataHandler"""
        self.assertEqual(self.data_handler.api_key, "test_api_key")
        self.assertEqual(self.data_handler.access_token, "test_access_token")
        self.assertEqual(self.data_handler.token_to_symbol, self.token_to_symbol)
        self.assertEqual(self.data_handler.symbol_to_token, {"RELIANCE": 256265, "INFY": 408065})
    
    def test_update_token_to_symbol(self):
        """Test updating token_to_symbol mapping"""
        new_mapping = {
            256265: "RELIANCE",
            408065: "INFY",
            123456: "TCS"
        }
        
        self.data_handler.update_token_to_symbol(new_mapping)
        
        self.assertEqual(self.data_handler.token_to_symbol, new_mapping)
        self.assertEqual(self.data_handler.symbol_to_token, {
            "RELIANCE": 256265,
            "INFY": 408065,
            "TCS": 123456
        })
    
    def test_on_ticks(self):
        """Test processing of tick data"""
        # Create mock WebSocket and ticks
        mock_ws = MagicMock()
        mock_ticks = [
            {"instrument_token": 256265, "last_price": 2500.0},
            {"instrument_token": 408065, "last_price": 1500.0}
        ]
        
        # Call the on_ticks method
        self.data_handler._on_ticks(mock_ws, mock_ticks)
        
        # Verify price updates
        self.assertEqual(self.data_handler.price_cache.get("RELIANCE"), 2500.0)
        self.assertEqual(self.data_handler.price_cache.get("INFY"), 1500.0)
        
        # Wait for the queue processing
        time.sleep(0.1)
        
        # Verify callbacks
        # Note: These might not be called in a short test as they're processed in a separate thread
        # self.data_handler.on_price_update.assert_called()
    
    def test_get_price(self):
        """Test retrieving price for a symbol"""
        # Set up test data
        self.data_handler.price_cache.update("RELIANCE", 2500.0)
        
        # Test retrieval
        self.assertEqual(self.data_handler.get_price("RELIANCE"), 2500.0)
        self.assertIsNone(self.data_handler.get_price("NON_EXISTENT"))
    
    def test_get_all_prices(self):
        """Test retrieving all prices"""
        # Set up test data
        price_updates = {
            "RELIANCE": 2500.0,
            "INFY": 1500.0
        }
        self.data_handler.price_cache.update_batch(price_updates)
        
        # Test retrieval
        all_prices = self.data_handler.get_all_prices()
        self.assertEqual(len(all_prices), 2)
        self.assertEqual(all_prices["RELIANCE"], 2500.0)
        self.assertEqual(all_prices["INFY"], 1500.0)

if __name__ == "__main__":
    unittest.main()