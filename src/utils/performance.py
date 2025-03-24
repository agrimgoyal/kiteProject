# src/utils/performance.py
import time
import logging
import psutil
import threading
from collections import deque, defaultdict
import os
from typing import Dict, List, Callable, Any, Optional

class PerformanceMonitor:
    """Real-time performance monitoring system"""
    
    def __init__(self, log_interval: int = 60):
        self.log_interval = log_interval
        self.function_timings = defaultdict(lambda: deque(maxlen=1000))
        self.process = psutil.Process()
        self.is_running = True
        
        # Track thread counts
        self.thread_counts = deque(maxlen=60)
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(
            target=self._monitor_thread,
            daemon=True,
            name="PerfMonitor"
        )
        self.monitor_thread.start()
    
    def time_function(self, func_name: str):
        """Decorator to time function execution"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start = time.time()
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                
                # Store timing
                self.function_timings[func_name].append(elapsed)
                
                # Log slow functions immediately
                if elapsed > 0.1:  # 100ms threshold for highlighting
                    logging.warning(f"SLOW FUNCTION: {func_name} took {elapsed:.3f}s to execute")
                
                return result
            return wrapper
        return decorator
    
    def _monitor_thread(self) -> None:
        """Background thread for periodic monitoring"""
        last_log_time = 0
        
        while self.is_running:
            try:
                # Track memory and CPU
                memory = self.process.memory_info().rss / 1024 / 1024  # MB
                cpu = self.process.cpu_percent(interval=0.1)
                
                # Track thread count
                thread_count = len(threading.enumerate())
                self.thread_counts.append(thread_count)
                    
                # Log periodically
                now = time.time()
                if (now - last_log_time) >= self.log_interval:
                    self._log_stats(memory, cpu)
                    last_log_time = now
                    
                time.sleep(1)
            except Exception as e:
                logging.error(f"Error in performance monitor: {e}")
                time.sleep(5)
    
    def _log_stats(self, memory: float, cpu: float) -> None:
        """Log performance statistics"""
        # Function timing stats
        timing_stats = []
        for func_name, timings in self.function_timings.items():
            if not timings:
                continue
                
            avg_time = sum(timings) / len(timings)
            max_time = max(timings)
            timing_stats.append((func_name, avg_time, max_time, len(timings)))
            
        # Sort by average time
        timing_stats.sort(key=lambda x: x[1], reverse=True)
        
        # Log top 5 slowest functions
        if timing_stats:
            logging.info("Top 5 slowest functions:")
            for i, (func_name, avg, max_time, count) in enumerate(timing_stats[:5]):
                logging.info(f"{i+1}. {func_name}: avg={avg:.3f}s, max={max_time:.3f}s, calls={count}")
        
        # Log system stats
        avg_threads = sum(self.thread_counts) / len(self.thread_counts) if self.thread_counts else 0
        logging.info(f"System stats: Memory={memory:.1f}MB, CPU={cpu:.1f}%, Threads={avg_threads:.1f}")
    
    def stop(self) -> None:
        """Stop the performance monitor"""
        self.is_running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)