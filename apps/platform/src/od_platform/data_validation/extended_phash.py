"""扩展点2：重型 Phash 重复/近重复图像检测。"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from od_platform.data_validation.extended_common import (
    ExtendedCheckResult,
    ExtendedIssue,
    iter_image_label_pairs,
    make_issue,
    severity_from_issues,
)
from od_platform.data_validation.registry import CheckSeverity
from od_platform.data_validation.snapshot import DatasetSnapshot, build_snapshot

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None  # type: ignore[assignment]


def average_hash(image_path: Path, hash_size: int = 8) -> Optional[str]:
    if Image is None:
        return None
    try:
        with Image.open(image_path) as image:
            gray = image.convert("L").resize((hash_size, hash_size))
            pixels = list(gray.getdata())
    except Exception:
        return None
    avg = sum(pixels) / len(pixels)
    bits = ["1" if pixel >= avg else "0" for pixel in pixels]
    return f"{int(''.join(bits), 2):0{hash_size * hash_size // 4}x}"


def hamming_distance(hex_left: str, hex_right: str) -> int:
    return bin(int(hex_left, 16) ^ int(hex_right, 16)).count("1")


def file_sha1(path: Path, chunk_size: int = 1024 * 1024) -> Optional[str]:
    digest = hashlib.sha1()
    try:
        with path.open("rb") as file_obj:
            while True:
                chunk = file_obj.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def check_phash_duplicates(
    snapshot: DatasetSnapshot,
    enabled: bool = True,
    hamming_threshold: int = 5,
    max_images: Optional[int] = None,
) -> Tuple[ExtendedCheckResult, List[ExtendedIssue]]:
    """使用感知哈希发现重复/近重复图像。"""
    if not enabled:
        return ExtendedCheckResult(
            name="phash_duplicates",
            severity=CheckSeverity.INFO,
            summary="Phash 重型检测未启用",
            issue_count=0,
            details={"enabled": False},
        ), []
    if Image is None:
        return ExtendedCheckResult(
            name="phash_duplicates",
            severity=CheckSeverity.INFO,
            summary="未安装 Pillow，无法执行 Phash 检测",
            issue_count=0,
            details={"enabled": True, "pillow_available": False},
        ), []

    rows = list(iter_image_label_pairs(snapshot))
    if max_images is not None:
        rows = rows[:max_images]

    hashes: List[Tuple[str, Path, Path, str, Optional[str]]] = []
    for split, image_path, label_path in rows:
        phash = average_hash(image_path)
        if phash is not None:
            hashes.append((split, image_path, label_path, phash, file_sha1(image_path)))

    issues: List[ExtendedIssue] = []
    for index, left in enumerate(hashes):
        left_split, left_image, left_label, left_hash, left_sha1 = left
        for right_split, right_image, _right_label, right_hash, right_sha1 in hashes[index + 1:]:
            distance = hamming_distance(left_hash, right_hash)
            if distance <= hamming_threshold:
                issue_type = "exact_duplicate" if left_sha1 and left_sha1 == right_sha1 else "near_duplicate"
                severity = CheckSeverity.WARNING if issue_type == "near_duplicate" else CheckSeverity.ERROR
                issues.append(make_issue(
                    "phash_duplicates", severity, left_split, left_image, left_label,
                    issue_type,
                    f"与 {right_image} 疑似重复，汉明距离={distance}",
                    "若为重复采样，请保留清晰且标注正确的一份；若跨划分重复，应重新划分避免数据泄露。",
                    duplicate_split=right_split,
                    duplicate_image=str(right_image),
                    phash=left_hash,
                    duplicate_phash=right_hash,
                    hamming_distance=distance,
                    hamming_threshold=hamming_threshold,
                ))
    return ExtendedCheckResult(
        name="phash_duplicates",
        severity=severity_from_issues(issues),
        summary="未发现重复/近重复图像" if not issues else f"发现 {len(issues)} 组重复/近重复图像",
        issue_count=len(issues),
        details={"enabled": True, "hamming_threshold": hamming_threshold, "hashed_images": len(hashes), "max_images": max_images},
    ), issues


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="扩展点2：运行重型 Phash 重复/近重复检测")
    parser.add_argument("--data", "--yaml", dest="yaml_path", required=True, type=Path, help="数据集 yaml 路径")
    parser.add_argument("--task", dest="task_type", default=None, help="任务类型: detect/segment，默认读取 yaml")
    parser.add_argument("--threshold", type=int, default=5, help="Phash 汉明距离阈值，越小越严格")
    parser.add_argument("--max-images", type=int, default=None, help="限制最大扫描图像数")
    parser.add_argument("--out", type=Path, default=None, help="可选：输出 JSON 结果路径")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = build_snapshot(args.yaml_path, task_type=args.task_type)
    result, issues = check_phash_duplicates(snapshot, enabled=True, hamming_threshold=args.threshold, max_images=args.max_images)
    payload = {"check": asdict(result), "issues": [issue.to_csv_row() for issue in issues]}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 2 if result.severity == CheckSeverity.ERROR else 0


if __name__ == "__main__":
    raise SystemExit(main())
