# scripts/benchmark.py
"""
Benchmark tool for measuring performance of critical components
"""
import sys
import os
import time
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
import logging
import json
import random

# Add the src directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.symbol_registry import SymbolRegistry, SymbolData
from src.core.market_data import PriceCache
from src.extensions.price_processor import PriceProcessor

def generate_test_data(num_symbols=100, num_price_updates=1000):
    """Generate test data for benchmarking"""
    print(f"Generating test data with {num_symbols} symbols and {num_price_updates} price updates...")
    
    # Generate symbol data
    symbols = []
    for i in range(num_symbols):
        symbol_name = f"SYMBOL{i+1}"
        price_base = random.uniform(100, 5000)
        
        # Randomly assign LONG or SHORT
        trade_type = "LONG" if random.random() > 0.5 else "SHORT"
        
        symbol_data = {
            "symbol": symbol_name,
            "token": 100000 + i,
            "trade_type": trade_type,
            "buffer": random.uniform(1.0, 5.0),
            "exchange": "NSE",
            "product_type": "CNC",
            "quantity": random.randint(1, 100),
            "timeframe": "DAILY",
            "current_price": price_base,
            "previous_close": price_base * random.uniform(0.98, 1.02),
            "target_price": price_base * (random.uniform(0.95, 0.99) if trade_type == "LONG" else random.uniform(1.01, 1.05)),
            "trigger_price": price_base * (random.uniform(0.96, 0.99) if trade_type == "LONG" else random.uniform(1.01, 1.04)),
            "gtt_price": price_base * (random.uniform(0.97, 0.99) if trade_type == "LONG" else random.uniform(1.01, 1.03)),
            "validity_date": "31-12-2025"
        }
        
        symbols.append(symbol_data)
    
    # Generate price updates
    price_updates = []
    symbol_names = [s["symbol"] for s in symbols]
    
    for i in range(num_price_updates):
        # Select random symbols for this update
        num_updates = random.randint(1, min(20, num_symbols))
        update_symbols = random.sample(symbol_names, num_updates)
        
        # Create price update
        update = {}
        for symbol in update_symbols:
            # Find base price
            base_price = next(s["current_price"] for s in symbols if s["symbol"] == symbol)
            # Random price change
            update[symbol] = base_price * random.uniform(0.98, 1.02)
        
        price_updates.append(update)
    
    return symbols, price_updates

def benchmark_symbol_registry(symbols, price_updates):
    """Benchmark the SymbolRegistry performance"""
    print("\nBenchmarking SymbolRegistry performance...")
    
    # Create registry
    registry = SymbolRegistry()
    
    # Measure time to add symbols
    start_time = time.time()
    for symbol_data in symbols:
        registry.add(SymbolData(**symbol_data))
    end_time = time.time()
    
    add_time = end_time - start_time
    print(f"Time to add {len(symbols)} symbols: {add_time:.6f} seconds")
    
    # Measure time to look up symbols
    start_time = time.time()
    for symbol_data in symbols:
        registry.get_by_symbol(symbol_data["symbol"])
    end_time = time.time()
    
    lookup_time = end_time - start_time
    print(f"Time to look up {len(symbols)} symbols: {lookup_time:.6f} seconds")
    
    # Measure time to update prices
    total_update_time = 0
    total_updates = 0
    
    for price_update in price_updates:
        start_time = time.time()
        registry.update_prices_batch(price_update)
        end_time = time.time()
        
        total_update_time += (end_time - start_time)
        total_updates += len(price_update)
    
    avg_update_time = total_update_time / len(price_updates)
    avg_per_symbol = total_update_time / total_updates
    
    print(f"Time to process {len(price_updates)} price updates: {total_update_time:.6f} seconds")
    print(f"Average time per update batch: {avg_update_time:.6f} seconds")
    print(f"Average time per symbol update: {avg_per_symbol:.9f} seconds")
    
    # Measure time to find potential triggers
    start_time = time.time()
    for _ in range(100):
        registry.get_potential_triggers()
    end_time = time.time()
    
    trigger_time = (end_time - start_time) / 100
    print(f"Average time to check for potential triggers: {trigger_time:.6f} seconds")
    
    return {
        "add_time": add_time,
        "lookup_time": lookup_time,
        "total_update_time": total_update_time,
        "avg_update_time": avg_update_time,
        "avg_per_symbol": avg_per_symbol,
        "trigger_time": trigger_time
    }

def benchmark_price_processor(symbols, price_updates):
    """Benchmark the PriceProcessor performance"""
    print("\nBenchmarking PriceProcessor performance...")
    
    # Create processor
    processor = PriceProcessor()
    
    # Set up symbol data
    start_time = time.time()
    for symbol_data in symbols:
        processor.set_symbol_data(
            symbol_data["symbol"],
            symbol_data["trade_type"],
            symbol_data["target_price"],
            symbol_data["trigger_price"],
            symbol_data["gtt_price"]
        )
    end_time = time.time()
    
    setup_time = end_time - start_time
    print(f"Time to set up {len(symbols)} symbols: {setup_time:.6f} seconds")
    
    # Measure time to update prices
    total_update_time = 0
    total_updates = 0
    
    for price_update in price_updates:
        start_time = time.time()
        processor.update_prices(price_update)
        end_time = time.time()
        
        total_update_time += (end_time - start_time)
        total_updates += len(price_update)
    
    avg_update_time = total_update_time / len(price_updates)
    avg_per_symbol = total_update_time / total_updates
    
    print(f"Time to process {len(price_updates)} price updates: {total_update_time:.6f} seconds")
    print(f"Average time per update batch: {avg_update_time:.6f} seconds")
    print(f"Average time per symbol update: {avg_per_symbol:.9f} seconds")
    
    # Measure time to find potential triggers
    start_time = time.time()
    for _ in range(100):
        processor.find_potential_triggers()
    end_time = time.time()
    
    trigger_time = (end_time - start_time) / 100
    print(f"Average time to check for potential triggers: {trigger_time:.6f} seconds")
    
    # Measure time to check triggers
    start_time = time.time()
    for _ in range(100):
        processor.check_triggers()
    end_time = time.time()
    
    check_time = (end_time - start_time) / 100
    print(f"Average time to check for triggers: {check_time:.6f} seconds")
    
    return {
        "setup_time": setup_time,
        "total_update_time": total_update_time,
        "avg_update_time": avg_update_time,
        "avg_per_symbol": avg_per_symbol,
        "trigger_time": trigger_time,
        "check_time": check_time
    }

def print_comparison(registry_results, processor_results):
    """Print comparison between different implementations"""
    print("\nPerformance Comparison:")
    print("-" * 60)
    print("Operation               | SymbolRegistry      | PriceProcessor      | Improvement")
    print("-" * 60)
    
    # Compare setup time
    setup_registry = registry_results["add_time"]
    setup_processor = processor_results["setup_time"]
    improvement = (setup_registry / setup_processor) if setup_processor > 0 else float('inf')
    print(f"Symbol Setup           | {setup_registry:.6f} s      | {setup_processor:.6f} s      | {improvement:.2f}x")
    
    # Compare update time
    update_registry = registry_results["avg_update_time"]
    update_processor = processor_results["avg_update_time"]
    improvement = (update_registry / update_processor) if update_processor > 0 else float('inf')
    print(f"Batch Price Update     | {update_registry:.6f} s      | {update_processor:.6f} s      | {improvement:.2f}x")
    
    # Compare per-symbol update time
    symbol_registry = registry_results["avg_per_symbol"]
    symbol_processor = processor_results["avg_per_symbol"]
    improvement = (symbol_registry / symbol_processor) if symbol_processor > 0 else float('inf')
    print(f"Per-Symbol Update      | {symbol_registry:.9f} s | {symbol_processor:.9f} s | {improvement:.2f}x")
    
    # Compare trigger check time
    trigger_registry = registry_results["trigger_time"]
    trigger_processor = processor_results["trigger_time"]
    improvement = (trigger_registry / trigger_processor) if trigger_processor > 0 else float('inf')
    print(f"Potential Trigger Check| {trigger_registry:.6f} s      | {trigger_processor:.6f} s      | {improvement:.2f}x")
    
    print("-" * 60)

def save_results(results, filename):
    """Save benchmark results to a file"""
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {filename}")

def main():
    parser = argparse.ArgumentParser(description="Benchmark the performance of KiteTrader components")
    parser.add_argument("--symbols", type=int, default=100, help="Number of symbols to generate")
    parser.add_argument("--updates", type=int, default=1000, help="Number of price update batches to generate")
    parser.add_argument("--output", type=str, default="benchmark_results.json", help="Output file for results")
    
    args = parser.parse_args()
    
    # Generate test data
    symbols, price_updates = generate_test_data(args.symbols, args.updates)
    
    # Run benchmarks
    registry_results = benchmark_symbol_registry(symbols, price_updates)
    processor_results = benchmark_price_processor(symbols, price_updates)
    
    # Print comparison
    print_comparison(registry_results, processor_results)
    
    # Save results
    results = {
        "parameters": {
            "num_symbols": args.symbols,
            "num_updates": args.updates,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "symbol_registry": registry_results,
        "price_processor": processor_results
    }
    save_results(results, args.output)

if __name__ == "__main__":
    main()