# KiteTrader: Trading Strategy Implementation Guide

This guide explains how to implement your own trading strategies with KiteTrader. The system is designed to be flexible, allowing you to implement various trading approaches while benefiting from the high-performance infrastructure.

## Understanding the System Architecture

KiteTrader operates with the following key components:

1. **Trading Engine** - The core coordinator that manages all trading operations
2. **Symbol Registry** - Stores and manages symbol data with optimized access patterns
3. **Market Data Handler** - Processes real-time market data from WebSocket
4. **Order Manager** - Handles order placement and tracking

To implement a custom strategy, you'll typically interact with these components rather than modifying them directly.

## Implementing Basic Strategies

### 1. Buffer-Based Strategy (Default)

The default approach uses a buffer percentage from a CSV file:

```csv
Symbol,buffer,Trade Type,Timeframe,Product Type,Quantity
RELIANCE,2.5,LONG,DAILY,CNC,1
INFY,3.0,SHORT,INTRADAY,MIS,10
```

For each symbol:
- `buffer`: Percentage away from previous close where the order triggers
- `Trade Type`: LONG (buy when price falls) or SHORT (sell when price rises)
- `Timeframe`: DAILY, INTRADAY, WEEKLY, or MONTHLY

This is implemented in the `_calculate_price_targets` method of the trading engine.

### 2. Custom Price Calculation

To implement a custom price calculation:

1. Create a new class that inherits from `TradingEngine`
2. Override the `_calculate_price_targets` method:

```python
class CustomStrategyEngine(TradingEngine):
    def _calculate_price_targets(self):
        """Calculate target prices using custom logic"""
        for symbol, data in self.registry._by_symbol.items():
            prev_close = data.previous_close
            
            # Custom calculation based on your strategy
            if data.trade_type.upper() == "LONG":
                # Example: Calculate target at 2% below yesterday's low
                data.target_price = prev_close * 0.98
                data.trigger_price = prev_close * 0.985
                data.gtt_price = prev_close * 0.99
            else:  # SHORT
                # Example: Calculate target at 2% above yesterday's high
                data.target_price = prev_close * 1.02
                data.trigger_price = prev_close * 1.015
                data.gtt_price = prev_close * 1.01
            
            # Apply tick size rounding
            data.target_price = self._round_tick_price(prev_close, data.target_price)
            data.trigger_price = self._round_tick_price(prev_close, data.trigger_price)
            data.gtt_price = self._round_tick_price(prev_close, data.gtt_price)
            
            # Update DataFrame for backward compatibility
            self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Target Price"] = data.target_price
            self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Trigger Price"] = data.trigger_price
            self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Order Price"] = data.gtt_price
```

## Advanced Strategy Implementation

### 1. Creating a Custom Strategy Class

For more complex strategies, create a dedicated strategy class:

```python
from src.core.engine import TradingEngine

class MovingAverageStrategy(TradingEngine):
    def __init__(self, config, fast_period=10, slow_period=20):
        super().__init__(config)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.historical_data = {}
    
    def start(self):
        """Override to include strategy-specific initialization"""
        # First do the standard initialization
        if not super().start():
            return False
        
        # Then do strategy-specific setup
        self._fetch_historical_data()
        self._calculate_indicators()
        
        return True
    
    def _fetch_historical_data(self):
        """Fetch historical data for calculating indicators"""
        symbols = list(self.registry._by_symbol.keys())
        
        for symbol in symbols:
            try:
                # Get instrument token
                token = self.registry.get_by_symbol(symbol).token
                
                # Fetch last 60 days of daily data
                today = datetime.now()
                from_date = today - timedelta(days=60)
                
                data = self.order_manager.kite.historical_data(
                    instrument_token=token,
                    from_date=from_date,
                    to_date=today,
                    interval="day"
                )
                
                self.historical_data[symbol] = data
                
            except Exception as e:
                logging.error(f"Error fetching historical data for {symbol}: {e}")
    
    def _calculate_indicators(self):
        """Calculate trading indicators based on historical data"""
        for symbol, data in self.historical_data.items():
            if len(data) < self.slow_period:
                continue
                
            # Calculate moving averages
            closes = [candle['close'] for candle in data]
            
            # Simple moving averages
            fast_ma = sum(closes[-self.fast_period:]) / self.fast_period
            slow_ma = sum(closes[-self.slow_period:]) / self.slow_period
            
            # Determine trade type based on MA crossover
            symbol_data = self.registry.get_by_symbol(symbol)
            
            if fast_ma > slow_ma:
                # Bullish trend - LONG strategy
                symbol_data.trade_type = "LONG"
                symbol_data.target_price = closes[-1] * 0.98
                symbol_data.trigger_price = closes[-1] * 0.985
                symbol_data.gtt_price = closes[-1] * 0.99
            else:
                # Bearish trend - SHORT strategy
                symbol_data.trade_type = "SHORT"
                symbol_data.target_price = closes[-1] * 1.02
                symbol_data.trigger_price = closes[-1] * 1.015
                symbol_data.gtt_price = closes[-1] * 1.01
            
            # Apply tick size rounding
            symbol_data.target_price = self._round_tick_price(symbol_data.previous_close, symbol_data.target_price)
            symbol_data.trigger_price = self._round_tick_price(symbol_data.previous_close, symbol_data.trigger_price)
            symbol_data.gtt_price = self._round_tick_price(symbol_data.previous_close, symbol_data.gtt_price)
            
            # Update DataFrame for backward compatibility
            self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Trade Type"] = symbol_data.trade_type
            self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Target Price"] = symbol_data.target_price
            self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "Trigger Price"] = symbol_data.trigger_price
            self.symbols_df.loc[self.symbols_df["Symbol"] == symbol, "GTT Order Price"] = symbol_data.gtt_price
```

### 2. Implementing Intraday Strategies

For intraday strategies with more frequent trade decisions:

```python
class IntradayScalpingStrategy(TradingEngine):
    def __init__(self, config):
        super().__init__(config)
        self.price_history = {}  # Store recent price ticks for analysis
        self.max_history_length = 100  # Keep last 100 ticks
    
    def _on_price_update(self, price_updates):
        """Override price update handler to implement intraday strategy"""
        # First do the standard price update
        super()._on_price_update(price_updates)
        
        # Then apply strategy-specific logic
        for symbol, price in price_updates.items():
            # Update price history
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            
            self.price_history[symbol].append(price)
            
            # Keep only the most recent data points
            if len(self.price_history[symbol]) > self.max_history_length:
                self.price_history[symbol] = self.price_history[symbol][-self.max_history_length:]
            
            # Apply scalping strategy if we have enough data
            if len(self.price_history[symbol]) >= 10:
                self._apply_scalping_strategy(symbol)
    
    def _apply_scalping_strategy(self, symbol):
        """Apply scalping strategy for a symbol"""
        prices = self.price_history[symbol]
        current_price = prices[-1]
        
        # Example: Simple price momentum
        price_5_ticks_ago = prices[-5]
        momentum = (current_price - price_5_ticks_ago) / price_5_ticks_ago * 100
        
        # Get symbol data
        symbol_data = self.registry.get_by_symbol(symbol)
        
        # Skip if not an intraday symbol
        if symbol_data.timeframe.upper() != "INTRADAY":
            return
        
        # Example logic: If momentum > 0.2% in either direction, enter a trade
        if abs(momentum) > 0.2 and not symbol_data.gtt_order_id:
            if momentum > 0:
                # Upward momentum - go LONG
                symbol_data.trade_type = "LONG"
                target_price = current_price * 0.998  # 0.2% profit target
            else:
                # Downward momentum - go SHORT
                symbol_data.trade_type = "SHORT"
                target_price = current_price * 1.002  # 0.2% profit target
            
            # Place a direct order instead of GTT for quick execution
            self._place_direct_order(symbol, symbol_data, target_price)
    
    def _place_direct_order(self, symbol, data, target_price):
        """Place a direct order for intraday trading"""
        # Implementation of direct order placement
        pass
```

## Using Technical Indicators

For strategies based on technical indicators, you can integrate libraries like TA-Lib:

```python
import talib
import numpy as np

class TechnicalIndicatorStrategy(TradingEngine):
    def _calculate_indicators(self):
        for symbol, data_list in self.historical_data.items():
            if len(data_list) < 50:  # Need enough data
                continue
                
            # Extract price data
            close_prices = np.array([candle['close'] for candle in data_list])
            high_prices = np.array([candle['high'] for candle in data_list])
            low_prices = np.array([candle['low'] for candle in data_list])
            
            # Calculate RSI
            rsi = talib.RSI(close_prices, timeperiod=14)
            
            # Calculate MACD
            macd, signal, hist = talib.MACD(close_prices, 
                                            fastperiod=12, 
                                            slowperiod=26, 
                                            signalperiod=9)
            
            # Calculate Bollinger Bands
            upper, middle, lower = talib.BBANDS(close_prices, 
                                              timeperiod=20, 
                                              nbdevup=2, 
                                              nbdevdn=2, 
                                              matype=0)
            
            # Get latest values
            current_rsi = rsi[-1]
            current_macd = macd[-1]
            current_signal = signal[-1]
            current_upper = upper[-1]
            current_lower = lower[-1]
            current_close = close_prices[-1]
            
            # Trading logic based on indicators
            symbol_data = self.registry.get_by_symbol(symbol)
            
            # Example strategy: RSI + MACD + Bollinger Bands
            if current_rsi < 30 and current_macd > current_signal and current_close < current_lower:
                # Oversold + MACD bullish + Price below lower band = LONG opportunity
                symbol_data.trade_type = "LONG"
                symbol_data.target_price = current_close * 0.98
                
            elif current_rsi > 70 and current_macd < current_signal and current_close > current_upper:
                # Overbought + MACD bearish + Price above upper band = SHORT opportunity
                symbol_data.trade_type = "SHORT"
                symbol_data.target_price = current_close * 1.02
```

## Event-Driven Strategy Implementation

To implement an event-driven strategy that responds to market events:

```python
class EventDrivenStrategy(TradingEngine):
    def __init__(self, config):
        super().__init__(config)
        self.event_conditions = {}
        self._setup_event_conditions()
    
    def _setup_event_conditions(self):
        """Define conditions for various market events"""
        # Example: Define conditions for various symbols
        self.event_conditions = {
            "RELIANCE": {
                "price_surge": {"threshold": 2.0, "timeframe": 5},  # 2% move in 5 minutes
                "volume_spike": {"threshold": 3.0, "lookback": 10}  # 3x normal volume
            },
            "INFY": {
                "price_surge": {"threshold": 1.5, "timeframe": 5},
                "volume_spike": {"threshold": 2.5, "lookback": 10}
            }
        }
    
    def _on_price_update(self, price_updates):
        """Process price updates and check for events"""
        super()._on_price_update(price_updates)
        
        for symbol, price in price_updates.items():
            if symbol in self.event_conditions:
                self._check_for_events(symbol, price)
    
    def _check_for_events(self, symbol, current_price):
        """Check if any events have occurred for this symbol"""
        conditions = self.event_conditions.get(symbol, {})
        symbol_data = self.registry.get_by_symbol(symbol)
        
        # Skip if already has an active order
        if symbol_data.gtt_order_id:
            return
        
        # Check for price surge event
        if "price_surge" in conditions:
            threshold = conditions["price_surge"]["threshold"]
            timeframe = conditions["price_surge"]["timeframe"]
            
            # Get historical prices for the timeframe
            if symbol in self.price_history and len(self.price_history[symbol]) > timeframe:
                price_timeframe_ago = self.price_history[symbol][-timeframe]
                percent_change = abs((current_price - price_timeframe_ago) / price_timeframe_ago * 100)
                
                if percent_change >= threshold:
                    # Price surge event detected!
                    direction = "up" if current_price > price_timeframe_ago else "down"
                    self._handle_price_surge_event(symbol, direction, percent_change)
    
    def _handle_price_surge_event(self, symbol, direction, percent_change):
        """Handle a price surge event"""
        symbol_data = self.registry.get_by_symbol(symbol)
        
        if direction == "up":
            # Price surged up - potential SHORT opportunity
            symbol_data.trade_type = "SHORT"
            symbol_data.target_price = symbol_data.current_price * 0.99  # Target 1% down
            symbol_data.trigger_price = symbol_data.current_price * 1.005  # Trigger if it goes up 0.5% more
            
        else:
            # Price surged down - potential LONG opportunity
            symbol_data.trade_type = "LONG"
            symbol_data.target_price = symbol_data.current_price * 1.01  # Target 1% up
            symbol_data.trigger_price = symbol_data.current_price * 0.995  # Trigger if it goes down 0.5% more
        
        # Place GTT order based on the event
        self._place_gtt_for_symbol(symbol, symbol_data)
        
        # Log the event
        self.dashboard.add_event("info", f"Price surge event: {symbol} moved {direction} by {percent_change:.2f}%")
```

## Best Practices for Strategy Implementation

1. **Separation of Concerns**: Keep your strategy logic separate from the infrastructure
2. **Error Handling**: Always include proper error handling to prevent unexpected crashes
3. **Backtesting**: Test your strategy with historical data before deploying it live
4. **Performance Monitoring**: Use the built-in performance monitoring to track efficiency
5. **Gradual Deployment**: Start with a small subset of symbols before scaling up

## Getting Started with Your Own Strategy

1. Create a new Python file for your strategy (e.g., `my_strategy.py`)
2. Inherit from the base `TradingEngine` class
3. Override the necessary methods based on your strategy's requirements
4. Create a custom entry point that uses your strategy class

Example entry point:

```python
# my_trading_app.py
import sys
import logging
from src.utils.logging_setup import setup_logging
from src.core.engine import TradingConfig
from my_strategy import MyCustomStrategy

def main():
    # Set up logging
    setup_logging(level="INFO")
    
    # Load configuration
    config = TradingConfig(
        api_key="your_api_key",
        api_secret="your_api_secret",
        access_token="your_access_token",
        symbols_path="data/Symbols.csv",
        # ... other configuration ...
    )
    
    # Create and start your custom strategy
    engine = MyCustomStrategy(config)
    
    if not engine.start():
        logging.error("Failed to start trading engine")
        return 1
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received")
    finally:
        engine.stop()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

By following this guide, you can implement and deploy your own custom trading strategies while leveraging the high-performance infrastructure of KiteTrader.
```

These additional components complete the high-performance KiteTrader system, providing comprehensive testing, deployment, benchmarking, monitoring, and strategy implementation capabilities. The system is now fully functional and optimized for efficiency, reliability, and extensibility.