# KiteTrader

A high-performance trading system for Zerodha's Kite Connect API, designed for efficiency and reliability.

## Structure

kitetrader/
├── config/
│   └── config.yaml
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── engine.py         # Core trading engine
│   │   ├── market_data.py    # Market data handling
│   │   ├── order_manager.py  # Order management
│   │   └── symbol_registry.py # Symbol data management
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logging_setup.py  # Logging configuration
│   │   ├── performance.py    # Performance monitoring
│   │   └── io_manager.py     # Optimized I/O operations
│   ├── extensions/
│   │   ├── __init__.py
│   │   └── price_processor.py # C++ extension wrapper
│   ├── __init__.py
│   └── main.py               # Application entry point
├── scripts/
│   ├── benchmark.py          # Performance benchmarking
│   └── setup_c_extensions.py # Setup C++ extensions
├── requirements.txt
└── README.md


## Features

- Event-driven architecture for minimal latency
- Optimized data structures for fast market data processing
- Advanced thread model with task specialization
- Memory-efficient design to handle large number of symbols
- Optional C++ extensions for critical path optimization
- Comprehensive error handling and recovery mechanisms
- Performance monitoring and diagnostics

## Installation

1. Clone the repository:
git clone https://github.com/agrimgoyal/kitetrader.git
cd kitetrader
2. Install dependencies:
pip install -r requirements.txt
3. (Optional) Build C++ extensions for improved performance:
python scripts/setup_c_extensions.py build_ext --inplace
## Configuration

Edit the `config/config.yaml` file with your Kite Connect API credentials and settings:

```yaml
# API Settings
api_key: "your_api_key_here"
api_secret: "your_api_secret_here"
access_token: "your_access_token_here"

# Data Files
symbols_path: "data/Symbols.csv"

# Trading Settings
test_mode: true  # Set to false for live trading
time_based_test_mode: true
gtt_expiry_time: "15:30:00"
intraday_time: "15:15:00"
trigger_threshold_adjustment: 0.25
max_orders_per_day: 3000
order_alert_threshold: 2550

# Advanced Settings
use_buffer_percentage: true
move_expired_orders: true
delete_orders_on_shutdown: false

Symbol Format
The trading symbols are specified in a CSV file with the following format:
| Symbol    | buffer | Trade Type | Timeframe | Product Type | Quantity |
|-----------|--------|------------|-----------|--------------|----------|
| RELIANCE  | 2.5    | LONG       | DAILY     | CNC          | 1        |
| INFY      | 3.0    | SHORT      | INTRADAY  | MIS          | 10       |

Required columns:

Symbol: Trading symbol as per Zerodha
buffer: Buffer percentage or price
Trade Type: LONG or SHORT

Optional columns that will be added if missing:

Timeframe: INTRADAY, DAILY, WEEKLY, MONTHLY
Product Type: CNC, MIS, NRML
Quantity: Number of shares/contracts to trade
Validity Date: Date until which order is valid (format: DD-MM-YYYY)

Usage
Run the trading system:
Copypython -m src.main

Command line options:

--config or -c: Path to configuration file (default: config/config.yaml)
--log-level or -l: Logging level (default: INFO)

Example:
Copypython -m src.main --config my_config.yaml --log-level DEBUG