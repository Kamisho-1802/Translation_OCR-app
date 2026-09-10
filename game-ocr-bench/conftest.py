"""リポジトリ直下を import パスに追加（editable install 前でも tests が動くように）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
