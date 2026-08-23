"""Run the synthetic-data laboratory CLI."""

import sys

from .cli import main
from .network_isolation import maybe_reexec_isolated

isolated_result = maybe_reexec_isolated(sys.argv[1:])
if isolated_result is not None:
    raise SystemExit(isolated_result)
raise SystemExit(main())
