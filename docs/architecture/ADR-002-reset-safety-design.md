# ADR-002: reset_project 双层防护与默认安全设计

| 字段 | 内容 |
|------|------|
| **ADR 编号** | ADR-002 |
| **标题** | reset_project 双层防护与默认安全设计 |
| **状态** | 已接受（Accepted） |
| **决策日期** | 2026-06-30 |
| **决策者** | 架构组 + 平台组 |
| **影响范围** | ODPlatform CLI 工具层 / 安全机制 |

---

## 1. 背景

ODPlatform D2.5 阶段需交付 `reset_project` 工具，用于安全地清理 `init_project` 创建的运行时产物。该工具的本质是面向文件系统的**批量破坏性操作**，与 `rm -rf` 功能等价，因此安全设计成为首要关注点。

### 1.1 痛点回顾

- 手工 `rm -rf` 路径拼写错误会导致不可逆的代码/数据丢失
- 缺乏删除前的"预览"能力，用户无法确认将要删除的内容
- 删除操作不可审计——事故发生后无法追溯
- CI 环境缺少标准化、非交互的清理命令
- 工具自身的日志可能被自己删除（自指 bug）

### 1.2 参考先例

| 工具 | dry-run 机制 |
|------|-------------|
| `git clean -n` | 默认只显示，`-f` 才删除 |
| `terraform plan` | 默认只显示变更，`apply` 才执行 |
| `kubectl --dry-run` | 预览效果，不实际应用 |
| `make -n` | 打印命令，不执行 |

业界共识：任何破坏性工具的默认行为应是只读/预演。

---

## 2. 备选方案

### 方案 A：仅 Allowlist（白名单）

- 仅定义可删除的目录列表
- 无第二层复核

**优点**：实现简单。

**缺点**：若 Allowlist 被人为误配置（如引入了 `.git`），无任何兜底拦截，灾难性后果。

### 方案 B：仅 Denylist（黑名单）

- 仅定义禁止删除的目录列表
- 任何不在黑名单中的目录均可删除

**优点**：实现简单。

**缺点**：黑名单不可能穷举所有危险路径；新增的敏感目录需要人工记得加入黑名单。**安全推断（"不在黑名单就安全"）不可靠**。

### 方案 C：双层防护（Two-layer Defense）✅ 选中

- 第一层（Allowlist）：删除清单仅来自 `get_dirs_to_reset()`，主动定义"可删什么"
- 第二层（Denylist）：`PROTECTED_DIRS` 复核，被动定义"绝不可删什么"
- 两层逻辑独立，互为冗余

**优点**：
- 单层失效不导致灾难
- 保护规则显式（Explicit over Implicit）
- 修改删除范围只需改一个函数（SSoT）

**缺点**：
- 实现略复杂（~15 行增量代码）
- 需要维护两个列表

---

## 3. 决定

采用**方案 C：双层防护**，并配合以下安全机制形成完整防线：

| 机制 | 说明 |
|------|------|
| **Safe by Default** | 未显式 `--yes` 时绝不执行删除；默认行为为 dry-run |
| **双层防护** | Allowlist (`get_dirs_to_reset`) + Denylist (`PROTECTED_DIRS` + `is_protected`) |
| **交互式二次确认** | `--yes` 但无 `--force` 时，要求用户精确输入大写 `RESET` |
| **Visual Interrupt** | 确认提示使用裸 `print()`（非 logger），强制视觉打断 |
| **Logger 隔离** | 工具日志写入 `META_LOGGING_DIR`，与业务 `LOGGING_DIR` 物理隔离 |
| **Fail-fast for ambiguity** | 第二层防护触发时立即整体中止，不允许部分执行 |
| **Best-effort for IO errors** | 执行期 IO 失败跳过该项，继续处理后续目录 |

### 3.1 双层防护示意

```
用户调用 reset_project(yes=True, force=True)
              │
              ▼
┌──────────────────────────────────────┐
│ 第一层（Allowlist）                   │
│ targets = paths.get_dirs_to_reset()  │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ 第二层（Denylist 复核）              │
│ for t in targets:                    │
│     if paths.is_protected(t):        │
│         abort(exit_code=2)           │
└──────────────┬───────────────────────┘
               │
               ▼
      实际执行删除流程
```

---

## 4. 后果

### 4.1 正面

- 误操作概率降为零（必须显式 `--yes`）
- 双层防护使代码 bug 或人为失误导致的数据损失风险降至最低
- 审计日志完整可追溯，满足公司数据治理合规要求
- CI 友好（`--yes --force` 无交互）
- 跨平台一致（Linux / macOS / Windows）

### 4.2 负面

- 用户首次使用时需多执行一次 dry-run 才能实际删除（但这是安全设计，非缺陷）
- 二次确认机制对自动化脚本不友好（但有 `--force` 替代路径）

### 4.3 中性

- 调整删除范围需修改 `paths.py` 中的 `get_dirs_to_reset()` 函数
- 调整保护列表需修改 `paths.py` 中的 `PROTECTED_DIRS` 常量

---

## 5. 撤销条件

以下任一条件满足时需重新评估本 ADR：

1. 平台目录架构发生重大变更（如不再采用 Monorepo + apps/ 布局）
2. 公司安全规范对删除操作提出更高要求
3. 引入新的存储后端（如 S3、MinIO）需要清理支持

---

## 6. 参考资料

- [ADR-001] 采用 Monorepo + apps/ 布局
- `git clean(1)` — dry-run 设计先例
- `terraform plan` — plan/apply 模式先例
- 《ODPlatform 通用工具层与项目初始化系统 PRD》（D2, ODP-PRD-2026-002）
- 《ODPlatform 项目重置工具 PRD》（D2.5, ODP-PRD-2026-003）
- 《数据资产分级与删除规范 v1.5》
- POSIX `unlink(2)` 与 Windows 文件锁语义
