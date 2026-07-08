"""生成 ultralytics 能直接吃的 dataset.yaml。"""
from __future__ import annotations

from pathlib import Path
from typing import List

from od_platform.data_pipeline.split.materializer import SplitOutputDirs


def write_dataset_yaml(
    yaml_path: Path,
    class_names: List[str],
    dirs: SplitOutputDirs,
) -> Path:
    """生成 dataset.yaml,返回写入的路径。

    Args:
        yaml_path: yaml 输出路径(如 configs/datasets/<name>.yaml)。
        class_names: 类别名列表,顺序即 class_id。
        dirs: 包含相对路径定义的 SplitOutputDirs。

    Returns:
        yaml_path(写入了内容)。
    """
    rel = dirs.relative_paths()
    # 数据根目录相对于 yaml 的路径
    # yaml 在 configs/datasets/<name>.yaml
    # 数据在 data/processed/<name>/train/images ...
    # 相对关系: ../../data/processed/<name>
    yaml_dir = yaml_path.parent.resolve()
    data_root_rel = _relative_to(dirs.train_images.parent.parent, yaml_dir)

    lines = [
        f"# ODPlatform auto-generated dataset\n",
        f"path: {data_root_rel.as_posix()}\n",
        f"train: {rel['train']}\n",
        f"val: {rel['val']}\n",
        f"test: {rel['test']}\n",
        f"\n",
        f"nc: {len(class_names)}\n",
        f"names: {class_names}\n",
    ]
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text("".join(lines), encoding="utf-8")
    return yaml_path


def _relative_to(target: Path, base: Path) -> Path:
    """计算 target 相对于 base 的相对路径(跨平台)。"""
    try:
        return target.resolve().relative_to(base.resolve())
    except ValueError:
        # 不在同一根下, 使用绝对路径
        return target.resolve()
