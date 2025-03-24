# scripts/setup_c_extensions.py
"""
Setup script for the C++ extensions used to optimize critical parts 
of the KiteTrader system.
"""
import os
import sys
import platform
import subprocess
from setuptools import setup, Extension
from distutils.command.build_ext import build_ext

class PriceProcessorExtension(Extension):
    def __init__(self):
        # Define source files
        sources = ['src/extensions/price_processor.cpp']
        
        # Initialize the extension
        Extension.__init__(self, 
                           'kitetrader.price_processor',
                           sources=sources,
                           include_dirs=[],
                           libraries=[],
                           library_dirs=[])

class BuildExt(build_ext):
    """Custom build extension to handle compiler flags"""
    
    def build_extensions(self):
        # Set appropriate compiler flags based on platform
        c_flags = []
        l_flags = []
        
        # Compiler-specific options
        if self.compiler.compiler_type == 'msvc':  # Microsoft Visual C++
            c_flags.append('/O2')  # Optimization level
            c_flags.append('/EHsc')  # Exception handling
            c_flags.append('/std:c++17')  # C++17 support
        else:  # GCC, Clang, etc.
            c_flags.append('-O3')  # Optimization level
            c_flags.append('-std=c++17')  # C++17 support
            c_flags.append('-fPIC')  # Position independent code
            
            # Additional platform-specific flags
            if platform.system() == 'Darwin':  # macOS
                c_flags.append('-stdlib=libc++')
                l_flags.append('-stdlib=libc++')
        
        # Set flags for all extensions
        for ext in self.extensions:
            ext.extra_compile_args = c_flags
            ext.extra_link_args = l_flags
        
        build_ext.build_extensions(self)

def main():
    """Main entry point for the setup script"""
    
    # Check if compiler is available
    try:
        # Try to detect C++ compiler
        from distutils.ccompiler import new_compiler
        compiler = new_compiler()
        
        # Print compiler info
        print(f"Using compiler: {compiler.compiler_type}")
        
    except Exception as e:
        print(f"Error detecting compiler: {e}")
        print("Please ensure you have a C++ compiler installed.")
        sys.exit(1)
    
    # Configure the extension
    price_processor_ext = PriceProcessorExtension()
    
    # Run setup
    setup(
        name="kitetrader_ext",
        version="0.1.0",
        description="C++ extensions for KiteTrader",
        ext_modules=[price_processor_ext],
        cmdclass={'build_ext': BuildExt},
    )
    
    print("C++ extensions built successfully!")

if __name__ == "__main__":
    main()