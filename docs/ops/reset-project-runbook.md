# ODPlatform reset_project 运维手册

## 1. 工具用途

`reset_project` 是 ODPlatform 平台的**项目重置工具**，用于安全、可控、可追溯地清理 `init_project` 创建的运行时产物，使工作区回到接近 `git clone` 后的状态。

**定位**：`init_project` 的反向操作，共同构成"环境生命周期管理"闭环。

## 2. 三种调用方式

| 方式 | 命令 | 适用场景 |
|------|------|---------|
| Console script | `odp-reset` | 安装后；推荐生产环境使用 |
| 模块路径 | `python -m od_platform.cli.reset_project` | 已安装；临时调试 |
| 开发期入口 | `python scripts/reset_project.py` | 未安装；开发期 / CI |

## 3. 命令参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--yes` | flag | False | 真正执行删除（默认是 dry-run） |
| `--force` | flag | False | 跳过交互式确认（仅当 `--yes` 时有效） |
| `--dry-run` | flag | False | 显式声明 dry-run |
| `-h` / `--help` | flag | — | 输出参数说明 |

**关键规则**：
- **默认 dry-run**：不带任何参数时仅预览，不删除任何文件
- `--yes` 执行真实删除前会要求交互确认（输入 `RESET`）
- `--yes --force` 跳过交互确认（CI 模式）

## 4. 常见使用场景

### 场景 1：首次清理（推荐流程）

```bash
cd ODPlatform

# 步骤 1：先查看将要删除什么
odp-reset

# 步骤 2：确认无误后，交互式执行删除
odp-reset --yes
# 提示输入时，精确输入大写的 RESET 并回车

# 步骤 3：检查结果
ls runs/         # 应已被删除
ls data/raw/     # 应保持不变
```

### 场景 2：CI 自动化

```bash
# 完全无交互清理
odp-reset --yes --force

# 检查退出码
if [ $? -ne 0 ]; then
    echo "重置失败，终止流水线"
    exit 1
fi
```

### 场景 3：仅在 CI 中预览（排查问题）

```bash
# 显式 dry-run，查看工具会删什么但不执行
odp-reset --dry-run
```

## 5. 退出码参考

| 退出码 | 场景 | CI 处置建议 |
|--------|------|------------|
| 0 | dry-run 完成 / 用户取消 / 全部删除成功 | 继续流水线 |
| 1 | 部分删除失败 | 检查日志后决定重试或人工介入 |
| 2 | 全部失败 / 双层防护触发 / 参数错误 | 立即终止流水线，人工介入 |

## 6. 删除范围

`reset_project` 仅删除以下运行时产物目录：

| 目录 | 说明 |
|------|------|
| `runs/` | 训练运行记录 |
| `models/checkpoints/` | 模型检查点 |
| `apps/platform/logging/` | 业务日志 |
| `data/train/` | 训练集缓存 |
| `data/val/` | 验证集缓存 |
| `data/test/` | 测试集缓存 |

**以下目录受保护，绝不会被删除**：
- `.git/`（版本控制）
- `apps/platform/src/`（源代码）
- `data/raw/`（原始数据）
- `models/pretrained/`（预训练权重）
- `docs/`、`scripts/`、`apps/platform/configs/`
- `apps/platform/meta_logging/`（审计日志自身）

## 7. 审计日志

每次执行（含 dry-run）均在 `apps/platform/meta_logging/reset_project/` 下生成独立审计日志。

### 日志文件命名

```
reset-project_<YYYYMMDD-HHMMSS-fff>_<PID>.log
```

### 日志格式

- 首行：`[AUDIT]` 前缀 + JSON 上下文（含执行者、时间、机器、git commit 等）
- 后续：标准 logger 输出（含扫描、决策、删除结果）

### 查阅方法

```bash
# 查看最近的审计日志
ls -t apps/platform/meta_logging/reset_project/ | head -5

# 提取审计上下文
head -1 apps/platform/meta_logging/reset_project/reset-project_*.log | python -m json.tool

# 查找特定用户的执行记录
grep '"user":"alice"' apps/platform/meta_logging/reset_project/*.log

# 统计执行次数
ls apps/platform/meta_logging/reset_project/*.log | wc -l
```

## 8. 故障排查

### 错误：`ModuleNotFoundError: No module named 'od_platform'`

**原因**：未安装包。

**解决**：
```bash
pip install -e ./apps/platform
# 或使用开发期入口
python scripts/reset_project.py --yes --force
```

### 错误：`找不到workspace marker文件`

**原因**：不在 ODPlatform 工作区目录下执行。

**解决**：`cd` 到仓库根目录（含 `.odp-workspace` 文件的目录）。

### 错误：Windows 上删除失败（PermissionError）

**原因**：某些文件被其他进程占用或标记为只读。

**解决**：
1. 确认所有相关程序（IDE、终端）已关闭该目录下的文件
2. reset_project 内置了只读文件 chmod 重试机制，一般无需手动处理
3. 若持续失败，查看审计日志中具体的失败路径和错误信息

### 问题：确认提示无法输入

**原因**：某些 IDE 终端可能吞掉 `input()` 调用。

**解决**：使用 `--yes --force` 跳过交互确认，或在外部终端（Windows Terminal / Git Bash）中执行。

## 9. 注意事项

- 删除操作**不可撤销**，建议首次使用先运行 dry-run 预览
- `--force` 不能单独使用（必须配合 `--yes`），单独 `--force` 等同于 dry-run
- 建议在重要操作前通过 git 提交或备份保护重要数据
- 审计日志保留 90 天，过期后由运维侧清理
