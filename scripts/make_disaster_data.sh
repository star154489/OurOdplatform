#!/bin/bash
# 为 D2 造灾难现场数据(用于 reset 压力测试)
set -e
echo "🎬 准备灾难现场..."

# 1. data/raw/ 假装放了珍贵标注(后面要保护它)
mkdir -p data/raw/precious_dataset/images data/raw/precious_dataset/labels
for i in $(seq 1 200); do
    echo "fake image $i" > "data/raw/precious_dataset/images/img_${i}.jpg"
    echo "0 0.5 0.5 0.3 0.4" > "data/raw/precious_dataset/labels/img_${i}.txt"
done
echo "  ✅ data/raw/precious_dataset/ — 400 个文件(模拟珍贵标注)"

# 2. runs/ 里造一个 2GB 稀疏文件(删它时会跑文件系统)
mkdir -p runs/exp_2026_05_10
dd if=/dev/zero of=runs/exp_2026_05_10/best.pt bs=1 count=0 seek=2G 2>/dev/null
echo "  ✅ runs/exp_2026_05_10/best.pt — 2 GB(稀疏文件)"

# 3. runs/ 里造 5000 个小文件(大量 inode,删起来真的慢)
mkdir -p runs/exp_2026_05_10/tb_logs
for i in $(seq 1 5000); do
    echo "step $i loss 0.${i}" > "runs/exp_2026_05_10/tb_logs/event.${i}"
done
echo "  ✅ runs/exp_2026_05_10/tb_logs/ — 5000 个小文件"

# 4. 一些已存在的日志(撞墙⑤的舞台)
mkdir -p apps/platform/logging/training/2026-05-10
for i in $(seq 1 50); do
    echo "training run $i log" > "apps/platform/logging/training/2026-05-10/run-${i}.log"
done
echo "  ✅ apps/platform/logging/ — 50 份训练日志"

echo "🎬 灾难现场准备就绪(总文件约 5650,名义约 2 GB)。"
du -sh data/raw runs apps/platform/logging 2>/dev/null
