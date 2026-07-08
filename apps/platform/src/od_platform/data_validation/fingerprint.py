"""数据集指纹 — 企业审计的第一问: 报告对应哪份数据?

设计取舍:
    - 指纹 = sha256(排序后的 "split/文件名:字节数" 清单)
      能抓: 增删文件 / 改名 / 文件大小变化 — 覆盖 95% 的"数据悄悄变了"
      抓不住: 同字节数的原地内容篡改
    - 清单只含文件名不含绝对路径 — 同一份数据换机器/换盘符指纹不变
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict

from od_platform.data_validation.snapshot import DatasetSnapshot


def compute_fingerprint(snapshot: DatasetSnapshot) -> Dict[str, Any]:
    """对快照中的全部图像与标签文件计算清单指纹。"""
    lines = []
    total_bytes = 0
    per_split: Dict[str, Dict[str, int]] = {}

    for split in snapshot.splits:
        split_bytes = 0
        images = snapshot.images_per_split.get(split, ())
        label_files = snapshot.label_files_per_split.get(split, ())

        for path in list(images) + list(label_files):
            try:
                size = path.stat().st_size
            except OSError:
                size = -1
            lines.append(f"{split}/{path.name}:{size}")
            if size > 0:
                split_bytes += size

        per_split[split] = {
            "images":      len(images),
            "label_files": len(label_files),
            "bytes":       split_bytes,
        }
        total_bytes += split_bytes

    lines.sort()
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    return {
        "manifest_sha256": digest,
        "total_files":     len(lines),
        "total_bytes":     total_bytes,
        "per_split":       per_split,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "algorithm":       "sha256(sorted 'split/filename:size') — 清单级指纹, 不含逐文件内容哈希",
    }
