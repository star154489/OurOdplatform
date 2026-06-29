from pathlib import Path
from typing import  List

from od_platform.common.paths import ROOT_DIR, get_dirs_to_initialize

def initialize_project() -> None:
    """
    初始化项目
    """
    print(f"初始化项目: {ROOT_DIR}")
    created: List[Path] = []
    existed: List[Path] = []
    
    for d in get_dirs_to_initialize():
        rel = d.relative_to(ROOT_DIR)
        if d.exists():
            print(f"目录已存在: {rel}")
            existed.append(d)
        else:
            d.mkdir(parents=True, exist_ok=True)
            created.append(d)
            print(f"创建目录: {rel}")
            
        print(f"初始化完成: 新建了{len(created)}个目录, 已经存在了{len(existed)}个目录")

if __name__ == "__main__":
    initialize_project()