"""GUI entry point and isolated native-build self-test."""
import sys
if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
    from launcher.healthcheck import run
    raise SystemExit(run(sys.argv[2]))
from launcher.app import main
main()
