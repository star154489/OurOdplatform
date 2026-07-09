# ODPlatform 完整功能手册（D0–D8）

> 以 **VOC_SHWD 数据集**（安全帽+人员检测）为例，从环境搭建到实时推理全流程。

---

## 一、安装

### 环境要求

| 项目 | 要求 |
|------|------|
| Python | ≥ 3.10，≤ 3.12 |
| 系统 | Windows 10/11、Linux、macOS |
| GPU（推荐） | NVIDIA GPU + CUDA 12+ |
| 磁盘 | 至少 5GB 可用空间 |

### 安装步骤

```bash
# 克隆或解压项目
cd ODPlatform
conda env remove --name odplat
# 创建虚拟环境（推荐）
conda create -n odplat python=3.12 -y
conda activate odplat

# 安装核心包（开发模式）
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu130

pip install ultralytics -U

pip install apps/platform

# 验证安装成功
odp-init
```

### 目录结构

```
ODPlatform/
├── apps/platform/src/od_platform/     核心代码
│   ├── common/                         D1: 路径/日志/工具
│   ├── cli/                            CLI 入口（8 个命令）
│   ├── data_pipeline/                  D3: 数据转换
│   ├── data_validation/                D4: 数据校验（14 项检查）
│   ├── runtime_config/                 D5: 运行配置（Pydantic）
│   ├── training/                       D6: 模型训练
│   ├── evaluation/                     D7: 模型评估
│   └── inference/                      D8: 实时推理
├── frame_source/                       D8: 帧输入源
├── data/raw/                           原始数据集
├── data/processed/                     转换后的 YOLO 数据集
├── configs/datasets/                   数据集 yaml
├── configs/runtime/                    运行配置 yaml
├── runs/                               运行时产物
├── models/pretrained/                  预训练权重
└── models/trained/                     已训练权重（归档）
```

---

## 二、D1：项目初始化

```bash
odp-init
```

创建 `data/`、`models/`、`runs/`、`configs/`、`logging/` 等全部骨架目录。

### 路径诊断

```bash
odp-paths
```

用于打印当前工作区根目录、运行时关键路径、初始化目标、重置目标、快照目标和受保护目录，适合快速检查工程组织规则是否符合预期。

---

## 三、D2：项目重置

### 命令

```bash
odp-reset                # 预览（默认，安全）
odp-reset --yes          # 交互式删除（需输入 RESET 确认）
odp-reset --yes --force  # CI 模式（无交互）
odp-reset --yes --backup # 删除前备份运行产物
```

### 删除范围

`data/processed/`、`runs/`、`logging/`、`configs/`、`models/trained/`、`models/checkpoints/`

### 保护范围（绝不会被删）

`data/raw/`（原始数据）、`models/pretrained/`（预训练权重）、`.git/`、`apps/`（代码）、`scripts/`、`docs/`、`meta_logging/`

### 运行产物备份与 manifest

当使用 `odp-reset --yes --backup` 时，工具会先把本次将被清理的运行产物打包到 `.odp-meta/backups/`，并同步生成同名 `.json` manifest，记录：

- 归档工具名
- 归档标签
- 生成时间
- 备份目标列表
- 目录数 / 文件数
- zip 路径

---

## 四、D3：数据转换与划分

### 命令

```bash
odp-transform --dataset <name> --format <fmt> [options]
```

### 操作

```bash
# 1. 先放置原始数据
#    data/raw/VOC_SHWD/images/       ← 图像（.jpg）
#    data/raw/VOC_SHWD/annotations/  ← 标注（.xml）

# 2. 执行转换
odp-transform --dataset VOC_SHWD --format pascal_voc
```

### 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `--dataset` | (必填) | 数据集名 |
| `--format` | (必填) | `pascal_voc` / `coco` / `yolo` |
| `--task` | `detect` | `detect` / `segment` |
| `--split-strategy` | `random` | 划分策略 |
| `--classes` | None | 类别白名单 |
| `--train-rate` | 0.8 | 训练集比例 |
| `--val-rate` | 0.1 | 验证集比例 |
| `--seed` | 1210 | 随机种子 |

### 输出

```
data/processed/VOC_SHWD/
├── train/images/ + labels/   ~6057 张
├── val/images/   + labels/   ~757 张
└── test/images/  + labels/   ~757 张

configs/datasets/VOC_SHWD.yaml  ← 供 ultralytics 和 D4/D6/D7 使用
```

---

## 五、D4：数据质量验证

### 命令

```bash
odp-validate --dataset VOC_SHWD
```

### 14 项检查

| # | 检查项 | 检测内容 |
|---|--------|---------|
| ① | yaml_schema | nc/names 一致性 |
| ② | pair_existence | 图像→标签成对 |
| ③ | label_format | 标签行格式 |
| ④ | split_uniqueness | 跨划分泄露 |
| ⑤ | bbox_within_image | 框出图 |
| ⑥ | box_geometry | 退化框+极端宽高比 |
| ⑦ | duplicate_annotations | 重复标注 |
| ⑧ | annotation_coverage | 无标注图占比 |
| ⑨ | orphan_labels | 孤儿标签 |
| ⑩ | stem_collision | 同名异扩展 |
| ⑪ | split_presence | 划分存在性 |
| ⑫ | class_presence | 类别出现性 |
| ⑬ | class_balance | 类别失衡 |
| ⑭ | image_integrity | 图像完整性（可选） |

### 退出码

| 码 | 含义 |
|----|------|
| 0 | 全部通过 |
| 1 | 有 WARNING |
| 2 | 有 ERROR |
| 3 | 工具异常 |

### 常用参数

```bash
odp-validate --dataset VOC_SHWD                   # 完整验证
odp-validate --dataset VOC_SHWD --no-profile       # 快速（跳过画像）
odp-validate --dataset VOC_SHWD --check-images     # 开图像解码检查
```

---

## 六、D5：运行配置管理

```bash
odp-gen-config train    # 生成训练配置模板
odp-gen-config val      # 生成验证配置模板
odp-gen-config infer    # 生成推理配置模板
```

生成的文件在 `configs/runtime/` 下，每个字段自带中文注释、示例值、提示。

---

## 六点五：项目快照

```bash
odp-snapshot
odp-backup
odp-snapshot --list
odp-snapshot --include src scripts
odp-snapshot --exclude docs
```

### 作用

- 对项目核心文件做 zip 快照
- 默认目标包括：`apps/platform/src/`、`docs/`、`scripts/`、`pyproject.toml`、`apps/platform/pyproject.toml`、`setup.py`
- 同步生成同名 manifest，记录快照目标和文件统计信息

### 可选化参数

| 参数 | 说明 |
|------|------|
| `--list` | 列出当前可选的快照目标名 |
| `--include` | 只打包指定目标，例如 `src scripts` |
| `--exclude` | 从默认目标中排除指定目标，例如 `docs` |

---

## 七、D6：模型训练

### 基本命令

```bash
odp-train --data VOC_SHWD --model yolo11n.pt --epochs 100
```

### 训练流程

```
D5 配置加载 → D4 数据校验 → D2 环境快照 → 配置溯源日志
→ ultralytics 训练 → 日志改名 → 权重归档 → 审计快照
```

### 常用参数

```bash
odp-train --data VOC_SHWD --model yolo11n.pt --epochs 100
odp-train --data VOC_SHWD --model yolo11s.pt --epochs 200 --batch 16 --device 0
odp-train --data VOC_SHWD --model yolo11n.pt --epochs 100 --experiment-name baseline_v1
odp-train --data VOC_SHWD --model yolo11n.pt --epochs 50 --no-archive
```

### 产物

- `runs/<task>_train/<exp>/weights/best.pt` — 最佳权重
- `models/trained/<model>_<dataset>_<timestamp>/best.pt` — 归档权重
- `runs/<task>_train/<exp>/od_audit.json` — 审计快照

---

## 八、D7：模型评估

### 命令

```bash
odp-val --model train-xxx-yolo11n-best.pt --data VOC_SHWD
```

### 设计特点

- **fail-fast**：模型找不到直接报错（不尝试下载）
- **不归档**：评估产出指标报告，不是新权重
- **不依赖训练模块**（单向依赖铁律）

---

## 九、D8：实时推理

### 命令

```bash
odp-infer --source 0 --model yolo11n.pt --show          # 摄像头
odp-infer --source demo.mp4 --model yolo11n.pt          # 视频文件
odp-infer --source ./images/ --model yolo11n.pt         # 图片文件夹
```

### 快捷键

| 按键 | 功能 |
|------|------|
| `q` / `Esc` | 退出 |
| `空格` | 暂停/恢复 |

### HUD 面板

```
Capture  29.8 FPS    ← 摄像头捕获帧率
Infer    63.2 FPS    ← 模型推理帧率
Render   34.1 FPS    ← 美化绘制帧率
Loop     29.5 FPS    ← 端到端吞吐
Current  31.2 FPS    ← 瞬时帧率
Objects  3           ← 检测数
```

---

## 十、VOC_SHWD 端到端工作流

```bash
# 0. 环境准备
conda activate odplat
cd ODPlatform
pip install -e apps/platform

# 1. D1: 初始化
odp-init
odp-paths

# 2. 放置数据到 data/raw/VOC_SHWD/{images/, annotations/}

# 3. D3: 数据转换
odp-transform --dataset VOC_SHWD --format pascal_voc

# 4. D4: 数据质检
odp-validate --dataset VOC_SHWD

# 5. D5: 生成训练配置
odp-gen-config train

# 6. D6: 训练
odp-train --data VOC_SHWD --model yolo11n.pt --epochs 100

# 7. D7: 评估
odp-val --model train-xxx-best.pt --data VOC_SHWD

# 8. D8: 实时推理
odp-infer --source 0 --model train-xxx-best.pt --show

# 9. 重置（下一轮实验）
odp-reset --yes --force

# 10. 项目快照（可选）
odp-snapshot
```

---

## 十一、命令速查

| 命令 | 功能 | 阶段 |
|------|------|------|
| `odp-init` | 项目初始化 | D1 |
| `odp-paths` | 路径诊断 | D1 |
| `odp-reset` | 安全清理 | D2 |
| `odp-snapshot` | 项目核心文件快照 | D2+ |
| `odp-backup` | 项目快照别名 | D2+ |
| `odp-transform` | 数据转换 | D3 |
| `odp-validate` | 数据质检 | D4 |
| `odp-gen-config` | 生成配置模板 | D5 |
| `odp-train` | 模型训练 | D6 |
| `odp-val` | 模型评估 | D7 |
| `odp-infer` | 实时推理 | D8 |
