"""让未安装状态下的 pytest 也能导入包源码。"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1]))
