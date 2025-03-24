# src/main.py
import logging
import signal
import sys
import os
import yaml
from datetime import datetime
import time
import argparse
from .core.engine import TradingEngine, TradingConfig
from .utils.logging_setup import setup_logging

def load_config(config_path, credentials_path=None):
    """Load configuration from YAML file with optional credentials file"""
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Load credentials if provided
        if credentials_path and os.path.exists(credentials_path):
            with open(credentials_path, 'r') as f:
                credentials_data = yaml.safe_load(f)
                # Merge credentials into config data
                config_data.update(credentials_data)
        print(config_data)
        
        # Create TradingConfig object
        trading_config = TradingConfig(
            api_key=config_data.get("api_key", ""),
            api_secret=config_data.get("api_secret", ""),
            access_token=config_data.get("access_token", ""),
            symbols_path=config_data.get("symbols_path", "Symbols.csv"),
            update_interval=config_data.get("update_interval", 1),
            test_mode=config_data.get("test_mode", True),
            time_based_test_mode=config_data.get("time_based_test_mode", True),
            gtt_expiry_time=config_data.get("gtt_expiry_time", "15:30:00"),
            auto_test_start_time=config_data.get("auto_test_start_time", "16:30:00"),
            auto_test_end_time=config_data.get("auto_test_end_time", "06:30:00"),
            intraday_time=config_data.get("intraday_time", "15:15:00"),
            trigger_threshold_adjustment=config_data.get("trigger_threshold_adjustment", 0.25),
            max_orders_per_day=config_data.get("max_orders_per_day", 3000),
            order_alert_threshold=config_data.get("order_alert_threshold", 2550),
            use_buffer_percentage=config_data.get("use_buffer_percentage", True),
            move_expired_orders=config_data.get("move_expired_orders", True),
            expired_orders_file=config_data.get("expired_orders_file", "expired_orders.csv"),
            completed_orders_file=config_data.get("completed_orders_file", "completed_orders.csv"),
            cleanup_time=config_data.get("cleanup_time", "16:00:00"),
            last_trading_day=config_data.get("last_trading_day", "FRI"),
            delete_orders_on_shutdown=config_data.get("delete_orders_on_shutdown", False),
        )
        
        return trading_config
    
    except Exception as e:
        logging.error(f"Error loading config: {e}")
        return None

def handle_signal(signum, frame, engine):
    """Handle system signals for graceful shutdown"""
    logging.info(f"Received signal {signum}, shutting down...")
    engine.stop()
    sys.exit(0)

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="KiteTrader - High-performance trading system")
    parser.add_argument("--config", "-c", 
                        default="config/config.yaml",
                        help="Path to base configuration file")
    parser.add_argument("--credentials", "-k",
                        default="config/kite_config.yaml",
                        help="Path to credentials configuration file")
    parser.add_argument("--log-level", "-l",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                        default="INFO",
                        help="Logging level")
    
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(level=args.log_level)
    
    logging.info("Starting KiteTrader...")
    
    # Load configuration
    config = load_config(args.config, args.credentials)
    if not config:
        logging.error("Failed to load configuration, exiting")
        return 1
    
    # Create and start the trading engine
    engine = TradingEngine(config)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, lambda signum, frame: handle_signal(signum, frame, engine))
    signal.signal(signal.SIGTERM, lambda signum, frame: handle_signal(signum, frame, engine))
    
    # Start the engine
    if not engine.start():
        logging.error("Failed to start trading engine")
        return 1
    
    logging.info(f"Trading engine running. Press Ctrl+C to stop.")
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received")
    finally:
        engine.stop()
        logging.info("Trading system stopped")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())