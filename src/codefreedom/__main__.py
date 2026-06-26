"""Allow running as `python -m codefreedom`."""
from __future__ import annotations

import sys

from codefreedom.cli.main import main

sys.exit(main())
