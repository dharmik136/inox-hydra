#!/usr/bin/env python3
"""
Convenience entry point for Inox Hydra real-time ingestion monitor.

Usage:
    python monitor.py
    python monitor.py --once
    python monitor.py --interval 1.0 --limit 10
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from studio.monitor import main

if __name__ == "__main__":
    sys.exit(main())
