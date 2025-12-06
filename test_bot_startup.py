#!/usr/bin/env python3
"""Quick test to see if bot starts properly."""

import sys
import signal
from bot.cli.main import main

def timeout_handler(signum, frame):
    print("\n⏱ Test timeout reached (10 seconds)")
    sys.exit(0)

# Set up timeout
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(10)  # 10 second timeout

try:
    print("Starting bot test...")
    main()
except KeyboardInterrupt:
    print("\n✓ Bot started successfully (interrupted by user)")
    sys.exit(0)
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

