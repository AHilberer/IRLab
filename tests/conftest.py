import os
import sys
import tempfile
from pathlib import Path

# make `servers`, `common`, ... importable when running pytest from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# server logs written by the tests go to a temporary directory, not to logs/
os.environ.setdefault('IRLAB_LOG_DIR', tempfile.mkdtemp(prefix='irlab_test_logs_'))
