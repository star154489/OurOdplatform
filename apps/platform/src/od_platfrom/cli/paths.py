from pathlib import Path
from typing import Tuple

# 找到Workspace根目录
WORKSPACE_MARKER: str = ".odp-workspace"


def _find_workspace_root(
    start: Path,
    markers: Tuple[str, ...] = (WORKSPACE_MARKER,),
) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for parent in [current, *current.parents]:
        for marker in markers:
            if (parent / marker).exists():
                return parent
    raise FileNotFoundError(
        f"找不到workspace marker文件({markers}) "
        f"请确认仓库根目录已存在{WORKSPACE_MARKER}文件"
    )


# 计算ROOT_DIR位置
ROOT_DIR: Path = _find_workspace_root(Path(__file__))
