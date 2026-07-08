# ODPlatform 需求规格说明书 · frame_source（帧源捕获）

| 项 | 内容 |
|---|---|
| **文档名称** | frame_source（帧源捕获）需求规格说明书 |
| **文档编号** | ODP-SRS-07 |
| **版本号** | V1.0 |
| **文档状态** | 已发布（Released） |
| **密级** | 内部公开（Internal） |
| **文档类型** | 软件需求规格说明书（SRS，子系统级） |
| **上级文档** | ODP-PRD-001 产品需求文档（总纲） |
| **主责角色** | 推理工程师 |
| **关联 ADR** | ADR-008（frame_source 门牌号：顶层平级、零宿主依赖；统一帧源抽象） |

### 修订记录

| 版本 | 日期 | 修订人 | 修订说明 |
|---|---|---|---|
| V1.0 | 2024-XX-XX | 推理工程师 | 初版定稿 |

---

## 1. 引言

### 1.1 目的

定义 **帧源子系统 `frame_source/`** 的功能需求、对外接口契约与验收标准。本模块把"出帧"这件事抽象为统一、可控、可整包移植的基础设施，填补底层框架官方输入接口"只读不写"的空白。

### 1.2 范围

提供图片、图片文件夹、视频、摄像头、RTSP 网络流五类输入源的统一迭代器抽象；支持摄像头参数协商（分辨率/帧率/后端/编码）与视频 seek；提供后台采集与异步包装。**本模块刻意零宿主依赖，设计目标是整包拷至任意 Python 项目即可用。**

### 1.3 模块在平台中的位置

```
   ┌──────────── 平等使用方（谁都不拥有它，谁都不反向依赖另一子系统）────────────┐
   │  inference（并发流水线）   未来 web-backend（serving）   评估/调试脚本        │
   └───────────────────────────────────┬───────────────────────────────────────┘
                                        │  统一 `for frame in src`
                                        ▼
                          ┌─────────────────────────────┐
                          │ frame_source 本模块（顶层平级）│  零宿主依赖、可整包拷走
                          └─────────────────────────────┘
```

> **门牌号判断（本模块最关键的物理位置决策）**：`frame_source/` 置于**顶层、与 `common/`、`inference/` 平级**，**不属于任何子系统**：
> 1. **不藏在 `inference/` 下**——否则未来 Web 端使用它须反向依赖推理子系统，耦合倒挂；
> 2. **不塞进 `common/`**——`common` 是"平台内部共享层"，而本模块立志"脱离本平台也能活"，物种不同；
> 3. **刻意零依赖宿主**（自带扩展名常量，不 `import common.constants`）——一旦引用宿主代码即拷不走。

### 1.4 术语补充

| 术语 | 释义 |
|---|---|
| 帧源（FrameSource） | 统一的"出帧"抽象，是迭代器 + 上下文管理器 |
| 参数协商 | 向摄像头 `set()` 请求参数后 `get()` 读回实际值（标称 vs 实测） |
| 后端（backend） | 跨平台采集后端（如 MSMF / DShow / V4L2） |
| seek | 跳转到视频指定时间/帧位 |
| 可整包拷走 | 整个目录复制到任意 Python 工程，仅改 import 前缀即可用 |

### 1.5 参考文档

ODP-PRD-001；ADR-008。**本模块不依赖任何其他子系统**。

---

## 2. 模块概述

### 2.1 职责（一句话）

> 让"图/视频/目录/摄像头/RTSP"在推理循环里长一个样——一个统一、可控、可整包拷走的出帧基础设施。

### 2.2 上下游

- **上游**：原始输入（设备/文件/网络流）。
- **下游**：推理（并发流水线）、未来 Web 端、调试脚本——**平等使用**，无人独占。

### 2.3 解决的痛点（回链总纲）

| 痛点 / 需求 | 本模块贡献 |
|---|---|
| PAIN-04 输入源僵化 | 填补官方"只读不写"空白，可显式配置（FR-D07-04） |
| 异构输入各写一套 | 五类源统一迭代器协议（FR-D07-01/02） |
| NFR-PORT-04 跨平台采集 | 后端协商 + 参数实测（FR-D07-04/05） |
| NFR-PORT-02 可移植 | 零宿主依赖 + README 移植说明（NFR-D07-01） |

---

## 3. 角色与交接

| 项 | 内容 |
|---|---|
| **主责** | 推理工程师 |
| **上游输入** | 设备/文件/网络流（由 `source` 字符串描述） |
| **下游交接物** | `create_frame_source(source)` 统一帧源 + `Frame.image`（BGR ndarray） |
| **可移植交付** | 模块自带 `README.md`（是什么/依赖/怎么拷走）与扩展名常量 |

---

## 4. 功能需求（FR）

| 编号 | 功能需求 | 优先级 | 验收要点 |
|---|---|---|---|
| FR-D07-01 | **统一帧源抽象**：`FrameSource` 基类同时是**迭代器**与**上下文管理器**；逐帧产出 `Frame`（含 `image` BGR ndarray 与 `FrameInfo` 元数据） | M | `with create_frame_source(src) as s: for frame in s: ...` 通用 |
| FR-D07-02 | **五类源**：图片、图片文件夹、视频、摄像头、RTSP 网络流，各有对应实现，下游切换源**零代码改动** | M | 五类源均可迭代出帧 |
| FR-D07-03 | **字符串自动识别 + fail-fast**：`create_frame_source("0"/路径/目录/视频/`rtsp://...`)` 自动判别源类型；路径不存在/格式不支持 **必须** `raise ValueError`；摄像头打不开由 `open()` 返回 `False` | M | 误输入立即报错并指明原因 |
| FR-D07-04 | **摄像头参数协商（填补官方空白）**：可**显式配置**分辨率/帧率/后端/编码，**不得**只读不写 | M | 可请求 720p/90fps 等并生效（受设备支持范围约束） |
| FR-D07-05 | **实测而非标称**：参数 `set()` 后必须 `get()` 读回实际值，对外暴露"实际生效参数"，**不得**以标称值欺骗调用方 | M | 实际分辨率/帧率可被读取 |
| FR-D07-06 | **视频 seek**：支持跳转到指定时间/帧位 | S | `seek` 后从目标位置出帧 |
| FR-D07-07 | **后台采集解耦**：提供 `ThreadedSource` 将采集放后台线程，与下游处理解耦 | S | 采集与处理可并行 |
| FR-D07-08 | **异步接口**：提供 `AsyncSource` 异步出帧包装 | C | async 迭代可用 |
| FR-D07-09 | **资源管理**：退出上下文/迭代结束**必须**释放底层资源（设备/文件句柄） | M | 无句柄泄漏 |

---

## 5. 对外接口契约（冻结）

> 调用方式：`from odp_platform.frame_source import <符号>`。**本模块无命令行入口**（基础设施库）。

### 5.1 公共 API（`__all__` 概览）

```python
from odp_platform.frame_source import (
    create_frame_source,          # (source, camera_config=None) -> FrameSource  字符串自动识别
    FrameSource,                  # 抽象基类：迭代器 + 上下文管理器
    Frame, FrameInfo,             # 单帧 / 帧元数据（FrameInfo 为 frozen dataclass）
    SourceType,                   # 源类型枚举
    CameraConfig,                 # 摄像头配置（Pydantic v2）
    CameraBackend, CameraCodec,   # 后端 / 编码枚举
    IMAGE_EXTENSIONS, VIDEO_EXTENSIONS,   # 自带扩展名常量（不依赖宿主）
)

# 用法契约
with create_frame_source("0") as src:        # "0"摄像头 / "x.jpg" / "dir/" / "x.mp4" / "rtsp://..."
    for frame in src:
        results = model(frame.image)          # frame.image 为 BGR ndarray

@dataclass(frozen=True)
class FrameInfo: ...      # 尺寸 / 帧号 / 时间戳

@dataclass
class Frame:
    image: "np.ndarray"  # BGR
    # + info 等
```

> 错误契约：路径不存在/格式不支持 → `raise ValueError`（fail-fast）；摄像头打不开 → `open()` 返回 `False`。

---

## 6. 模块级非功能需求

| 编号 | 需求 | 优先级 |
|---|---|---|
| NFR-D07-01 | **零宿主依赖（最关键）**：**不得** `import odp_platform.common` 或任何宿主子系统；自带 `IMAGE_EXTENSIONS`/`VIDEO_EXTENSIONS`（CON-08） | M |
| NFR-D07-02 | **可整包移植**：随附 `README.md`，仅改 import 前缀即可用（NFR-PORT-02） | M |
| NFR-D07-03 | **跨平台采集**：摄像头后端跨 Win/Linux/macOS 协商；采集失败**显式告警**，不静默降级（NFR-PORT-01/04） | M |
| NFR-D07-04 | **不反向依赖任何子系统**：作为顶层平级模块，不被任一子系统拥有 | M |

---

## 7. 约束与依赖

- **约束**：CON-08（核心）、NFR-PORT-01/02/04。
- **上游依赖**：无（顶层独立模块）。
- **外部依赖**：OpenCV；Pydantic v2（仅 `CameraConfig`）；numpy。**不依赖宿主项目。**

---

## 8. 验收标准与测试要点

| 类型 | 验收点 |
|---|---|
| 单元测试 | 五类源迭代正确；字符串识别正确；非法输入 fail-fast；资源释放；seek 行为 |
| 可移植守门 | grep：模块内无 `import odp_platform.common`（验证 NFR-D07-01）；附 README |
| 跨平台 | 三平台摄像头后端协商；参数 set/get 实测一致（NFR-PORT-04） |
| 移植验证 | 整包拷至空白工程，仅改 import 前缀即可 `for frame in src`（NFR-PORT-02） |

---

## 9. 工作分解（WBS）与提交序列

```
feat(frame_source): add core types (SourceType / FrameInfo / Frame) + extension SSoT
feat(frame_source): add FrameSource ABC (iterator + context manager) + CameraConfig
feat(frame_source): add ImageSource / ImageFolderSource
feat(frame_source): add VideoSource with seek
feat(frame_source): add CameraSource with cross-platform backend + param negotiation
feat(frame_source): add factory create_frame_source (string auto-detect, fail-fast)
feat(frame_source): add ThreadedSource / AsyncSource wrappers
docs(frame_source): add README (portability guide) + ADR-008
test(frame_source): add unit tests for all sources
```

---

## 10. 关联 ADR

| ADR | 决策（一句话） |
|---|---|
| ADR-008 | `frame_source` 置顶层平级、零宿主依赖、可整包拷走；以统一迭代器抽象五类输入源，填补官方"只读不写"空白 |

---

## 11. 需求追溯

| FR / NFR | 追溯至总纲 |
|---|---|
| FR-D07-02/03 | NFR-EXT-01、SCOPE-07 |
| FR-D07-04/05 | PAIN-04、NFR-PORT-04 |
| NFR-D07-01/02 | CON-08、NFR-PORT-02 |

---

*ODP-SRS-07 · frame_source 需求规格 · V1.0 · 隶属 ODP-PRD-001*
