"""python -m asset_agent <command>: the asset-agent CLI without its generated .exe (which Windows Smart App
Control can block)."""
import sys

from .cli import main

sys.exit(main())
