#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ODPlatform 桌面端 —— 一站式目标检测开发工具。

提供数据转换、验证、训练、评估、推理五大功能的图形化入口。
"""
from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# ── 全局日志队列(线程安全) ──────────────────────────────────
_log_queue: queue.Queue[str] = queue.Queue()
_logger = logging.getLogger("od_desktop")


class _QueueHandler(logging.Handler):
    """将 logging 消息推入队列,供 GUI 轮询消费。"""
    def emit(self, record: logging.LogRecord) -> None:
        _log_queue.put(self.format(record))


def _setup_logging() -> None:
    """配置根 logger:控制台 + 队列双输出。"""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    # 控制台
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S"))
    root.addHandler(ch)
    # 队列(供 GUI)
    qh = _QueueHandler()
    qh.setLevel(logging.INFO)
    qh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S"))
    root.addHandler(qh)


# ── 工具函数 ──────────────────────────────────────────────────


def _format_list(items: list[str]) -> str:
    return ", ".join(items)


def _available_formats() -> list[str]:
    from od_platform.data_pipeline.convert.registry import available_formats as _af
    return _af()


def _available_strategies() -> list[str]:
    from od_platform.data_pipeline.split.strategy_registry import available_strategies as _as
    return _as()


# ── 通用带日志输出的可滚动 Frame ─────────────────────────────


class ConsoleFrame(ttk.Frame):
    """一个带"清空"按钮和只读滚动文本框的控制台面板。"""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        ttk.Button(self, text="清空日志", command=self.clear).grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.text = tk.Text(self, wrap=tk.WORD, state=tk.DISABLED,
                            font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4",
                            insertbackground="white")
        sb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")

    def write(self, message: str) -> None:
        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, message + "\n")
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def clear(self) -> None:
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)


# ── 任务执行器(子进程) ───────────────────────────────────────


def run_in_thread(cmd: list[str], console: ConsoleFrame) -> None:
    """在线程中运行子进程,实时输出到 ConsoleFrame。"""
    console.clear()
    console.write(f"> {' '.join(cmd)}\n")
    console.write("─" * 60)

    def _target() -> None:
        try:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            for line in proc.stdout:
                console.write(line.rstrip())
            proc.wait()
            if proc.returncode == 0:
                console.write("\n✓ 完成")
            else:
                console.write(f"\n✗ 退出码: {proc.returncode}")
        except Exception as e:
            console.write(f"\n✗ 错误: {e}")

    threading.Thread(target=_target, daemon=True).start()


# ── 表单工具 ──────────────────────────────────────────────────


def _labeled_combo(parent, text: str, values: list[str], default: str, row: int, **kw) -> ttk.Combobox:
    ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", padx=(0, 5), pady=2)
    cb = ttk.Combobox(parent, values=values, state="readonly", **kw)
    cb.set(default)
    cb.grid(row=row, column=1, sticky="ew", pady=2)
    return cb


def _labeled_entry(parent, text: str, default: str, row: int, **kw) -> ttk.Entry:
    ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", padx=(0, 5), pady=2)
    var = tk.StringVar(value=default)
    e = ttk.Entry(parent, textvariable=var, **kw)
    e.grid(row=row, column=1, sticky="ew", pady=2)
    return e, var


def _labeled_scale(parent, text: str, from_, to_, default: float, row: int) -> tuple[ttk.Scale, tk.DoubleVar]:
    ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", padx=(0, 5), pady=2)
    var = tk.DoubleVar(value=default)
    sc = ttk.Scale(parent, from_=from_, to=to_, variable=var, orient=tk.HORIZONTAL)
    sc.grid(row=row, column=1, sticky="ew", pady=2)
    lbl = ttk.Label(parent, text=f"{default:.0%}")
    lbl.grid(row=row, column=2, padx=(2, 0))
    var.trace_add("write", lambda *_, v=var, l=lbl: l.configure(text=f"{v.get():.0%}"))
    return sc, var


def _browse_button(parent, entry_var: tk.StringVar, row: int, default_path: str = "") -> None:
    """在 row 的 column=2 处放一个浏览按钮,点击后把选中的【目录】路径写入 entry_var。"""
    def _browse() -> None:
        path = filedialog.askdirectory(title="选择目录", initialdir=default_path or None)
        if path:
            entry_var.set(path)
    ttk.Button(parent, text="浏览", command=_browse).grid(row=row, column=2, padx=(2, 0))


def _browse_file_button(parent, entry_var: tk.StringVar, row: int, default_path: str = "",
                        filetypes: list | None = None) -> None:
    """在 row 的 column=2 处放一个浏览按钮,点击后把选中的【文件】路径写入 entry_var。"""
    if filetypes is None:
        filetypes = [("所有文件", "*.*")]
    def _browse() -> None:
        path = filedialog.askopenfilename(
            title="选择文件", filetypes=filetypes,
            initialdir=default_path or None,
        )
        if path:
            entry_var.set(path)
    ttk.Button(parent, text="浏览", command=_browse).grid(row=row, column=2, padx=(2, 0))


# ── 各功能页面 ────────────────────────────────────────────────


class TransformPage(ttk.Frame):
    """数据转换 —— 将原始标注转换为可训练数据集。"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)

        # 表单区
        form = ttk.LabelFrame(self, text="转换参数", padding=10)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._ds_entry, self._ds_var = _labeled_entry(form, "数据集名称:", "demo_voc", 0, width=30)
        _browse_button(form, self._ds_var, 0)

        self._fmt_cb = _labeled_combo(form, "标注格式:", _available_formats(), "pascal_voc", 1)

        self._task_cb = _labeled_combo(form, "任务类型:", ["detect", "segment"], "detect", 2)

        self._strategy_cb = _labeled_combo(form, "划分策略:", _available_strategies(), "random", 3)

        self._train_sc, self._train_var = _labeled_scale(form, "训练比例:", 0.1, 0.95, 0.7, 4)
        self._val_sc, self._val_var = _labeled_scale(form, "验证比例:", 0.0, 0.4, 0.15, 5)

        _, self._seed_var = _labeled_entry(form, "随机种子:", "1210", 6, width=10)
        _, self._classes_var = _labeled_entry(form, "类别白名单(可选):", "", 7, width=30)

        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=8, column=0, columnspan=3, pady=(8, 0))
        ttk.Button(btn_frame, text="▶ 开始转换", command=self._run).pack(side=tk.LEFT, padx=2)

        # 日志区
        self.console = ConsoleFrame(self)
        self.console.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def _run(self) -> None:
        dataset = self._ds_var.get().strip()
        fmt = self._fmt_cb.get()
        task = self._task_cb.get()
        strategy = self._strategy_cb.get()
        train_rate = round(self._train_var.get(), 2)
        val_rate = round(self._val_var.get(), 2)
        seed = self._seed_var.get().strip() or "1210"
        classes = self._classes_var.get().strip()

        if not dataset:
            messagebox.showwarning("缺少参数", "请输入数据集名称")
            return

        cmd = [
            sys.executable, "-m", "od_platform.cli.transform_data",
            "--dataset", dataset,
            "--format", fmt,
            "--task", task,
            "--split-strategy", strategy,
            "--train-rate", str(train_rate),
            "--val-rate", str(val_rate),
            "--seed", seed,
        ]
        if classes:
            cmd.extend(["--classes"] + classes.split())

        run_in_thread(cmd, self.console)


class ValidatePage(ttk.Frame):
    """数据验证 —— 对 transform 产出的 yaml 做全面质量检查。"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        form = ttk.LabelFrame(self, text="验证参数", padding=10)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        # 数据集名称 / yaml 路径 (二选一)
        ttk.Label(form, text="数据集名称 (或 yaml 路径):").grid(row=0, column=0, sticky="w", padx=(0, 5), pady=2)
        self._ds_var = tk.StringVar()
        ds_frame = ttk.Frame(form)
        ds_frame.grid(row=0, column=1, sticky="ew")
        self._ds_entry = ttk.Entry(ds_frame, textvariable=self._ds_var, width=35)
        self._ds_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _browse_yaml():
            path = filedialog.askopenfilename(
                title="选择 dataset.yaml",
                filetypes=[("YAML 文件", "*.yaml"), ("所有文件", "*.*")],
                initialdir=str(Path.cwd() / "apps" / "platform" / "configs" / "datasets"),
            )
            if path:
                self._ds_var.set(path)
        ttk.Button(ds_frame, text="浏览 .yaml", command=_browse_yaml).pack(side=tk.LEFT, padx=(2, 0))

        ttk.Label(form, text="输入 transform 产出的数据集名 (如 VOC_SHWD)\n或直接选 yaml 文件路径",
                  font=("", 8), foreground="gray").grid(row=1, column=1, sticky="w", pady=(0, 4))

        # 可选开关
        opts_frame = ttk.Frame(form)
        opts_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        self._check_img_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="图像完整性检查 (逐张解码, 重型)", variable=self._check_img_var).pack(anchor="w")

        self._no_profile_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts_frame, text="跳过实例画像 (推荐 — 大数据集快 10-100 倍)", variable=self._no_profile_var).pack(anchor="w")

        self._no_headers_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="不读图像头 (进一步省 I/O)", variable=self._no_headers_var).pack(anchor="w")

        self._no_report_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="不写报告文件 (只看日志)", variable=self._no_report_var).pack(anchor="w")

        self._verbose_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts_frame, text="详细日志 (DEBUG 级别)", variable=self._verbose_var).pack(anchor="w")

        ttk.Button(form, text="▶ 开始验证", command=self._run).grid(row=3, column=1, sticky="w", pady=(8, 0))

        self.console = ConsoleFrame(self)
        self.console.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def _run(self) -> None:
        ref = self._ds_var.get().strip()
        if not ref:
            messagebox.showwarning("缺少参数", "请输入数据集名称 (如 VOC_SHWD) 或选择 yaml 文件")
            return

        # 自动判断是 yaml 路径还是数据集名称
        p = Path(ref)
        if p.is_absolute() or (p.suffix == ".yaml" and p.exists()):
            cmd = [sys.executable, "-m", "od_platform.cli.validate_data", "--yaml", ref]
        else:
            cmd = [sys.executable, "-m", "od_platform.cli.validate_data", "--dataset", ref]

        if self._check_img_var.get():
            cmd.append("--check-images")
        if self._no_profile_var.get():
            cmd.append("--no-profile")
        if self._no_headers_var.get():
            cmd.append("--no-image-headers")
        if self._no_report_var.get():
            cmd.append("--no-report")
        if self._verbose_var.get():
            cmd.append("--verbose")

        run_in_thread(cmd, self.console)


class TrainPage(ttk.Frame):
    """模型训练 —— 用 dataset.yaml 训练 YOLO 模型。"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        form = ttk.LabelFrame(self, text="训练参数", padding=10)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._yaml_entry, self._yaml_var = _labeled_entry(form, "数据集 YAML:", "", 0, width=30)
        _browse_file_button(form, self._yaml_var, 0,
                            str(Path.cwd() / "apps" / "platform" / "configs" / "datasets"),
                            filetypes=[("YAML 文件", "*.yaml"), ("所有文件", "*.*")])

        self._model_cb = _labeled_combo(form, "模型:", ["yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt",
                                                         "yolo12n.pt", "yolo12s.pt", "yolo12m.pt",
                                                         "yolo26n.pt", "yolo26s.pt"], "yolo11n.pt", 1)
        _, self._epochs_var = _labeled_entry(form, "轮次:", "100", 2, width=10)
        _, self._imgsz_var = _labeled_entry(form, "图像尺寸:", "640", 3, width=10)
        _, self._batch_var = _labeled_entry(form, "Batch:", "16", 4, width=10)
        _, self._name_var = _labeled_entry(form, "实验名:", "", 5, width=20)

        ttk.Button(form, text="▶ 开始训练", command=self._run).grid(row=6, column=1, sticky="w", pady=(8, 0))

        self.console = ConsoleFrame(self)
        self.console.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def _run(self) -> None:
        yaml = self._yaml_var.get().strip()
        if not yaml:
            messagebox.showwarning("缺少参数", "请选择数据集 YAML")
            return
        name = self._name_var.get().strip() or None
        cmd = [
            sys.executable, "-m", "od_platform.cli.train_model",
            "--data", yaml,
            "--model", self._model_cb.get(),
            "--epochs", self._epochs_var.get().strip(),
            "--imgsz", self._imgsz_var.get().strip(),
            "--batch", self._batch_var.get().strip(),
        ]
        if name:
            cmd.extend(["--experiment-name", name])
        run_in_thread(cmd, self.console)


class EvalPage(ttk.Frame):
    """模型评估 —— 在验证集上评估已训练模型。"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        form = ttk.LabelFrame(self, text="评估参数", padding=10)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        _, self._weights_var = _labeled_entry(form, "权重文件:", "", 0, width=30)
        _browse_file_button(form, self._weights_var, 0,
                            str(Path.cwd() / "models" / "trained"),
                            filetypes=[("PyTorch 权重", "*.pt"), ("所有文件", "*.*")])

        _, self._yaml_var = _labeled_entry(form, "数据集 YAML (名称或路径):", "", 1, width=30)
        _browse_file_button(form, self._yaml_var, 1,
                            str(Path.cwd() / "apps" / "platform" / "configs" / "datasets"),
                            filetypes=[("YAML 文件", "*.yaml"), ("所有文件", "*.*")])

        ttk.Button(form, text="▶ 开始评估", command=self._run).grid(row=2, column=1, sticky="w", pady=(8, 0))

        self.console = ConsoleFrame(self)
        self.console.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def _run(self) -> None:
        weights = self._weights_var.get().strip()
        yaml = self._yaml_var.get().strip()
        if not weights:
            messagebox.showwarning("缺少参数", "请选择权重文件")
            return
        if not yaml:
            messagebox.showwarning("缺少参数", "请输入数据集名称或 yaml 路径")
            return
        cmd = [
            sys.executable, "-m", "od_platform.cli.evaluate_model",
            "--model", weights,
            "--data", yaml,
        ]
        run_in_thread(cmd, self.console)


class InferPage(ttk.Frame):
    """模型推理 —— 对图片/视频/摄像头执行目标检测。"""

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        form = ttk.LabelFrame(self, text="推理参数", padding=10)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        _, self._weights_var = _labeled_entry(form, "权重文件:", "", 0, width=30)
        _browse_file_button(form, self._weights_var, 0,
                            str(Path.cwd() / "models" / "trained"),
                            filetypes=[("PyTorch 权重", "*.pt"), ("所有文件", "*.*")])

        self._source_mode = tk.StringVar(value="image")
        ttk.Label(form, text="输入类型:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=2)
        rm = ttk.Frame(form)
        rm.grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(rm, text="图片/视频", variable=self._source_mode, value="image").pack(side=tk.LEFT)
        ttk.Radiobutton(rm, text="摄像头", variable=self._source_mode, value="camera").pack(side=tk.LEFT)

        _, self._source_var = _labeled_entry(form, "输入路径:", "", 2, width=30)
        # 图片/视频用文件浏览，摄像头用数字输入
        self._browse_btn_frame = ttk.Frame(form)
        self._browse_btn_frame.grid(row=2, column=2, padx=(2, 0))
        self._browse_btn = ttk.Button(self._browse_btn_frame, text="浏览...",
                                       command=lambda: self._browse_source())
        self._browse_btn.pack()

        self._source_mode.trace_add("write", self._on_source_mode_change)
        # 构造时强设一次 (trace 不响应初始值)
        self._on_source_mode_change()

        self._show_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="弹窗显示检测画面 (按 Q 退出)", variable=self._show_var).grid(row=3, column=1, sticky="w")

        ttk.Button(form, text="▶ 开始推理", command=self._run).grid(row=4, column=1, sticky="w", pady=(8, 0))

        self.console = ConsoleFrame(self)
        self.console.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def _browse_source(self) -> None:
        if self._source_mode.get() == "camera":
            return  # 摄像头不需要浏览
        # 图片/视频模式: 优先选目录, 也可以选单个文件
        path = filedialog.askdirectory(
            title="选择图片目录",
            initialdir=str(Path.cwd() / "data" / "raw"),
        )
        if not path:  # 用户取消目录选择 → 尝试选文件
            path = filedialog.askopenfilename(
                title="选择图片或视频文件",
                filetypes=[("图片/视频", "*.jpg *.jpeg *.png *.bmp *.mp4 *.avi *.mov"), ("所有文件", "*.*")],
                initialdir=str(Path.cwd() / "data" / "raw"),
            )
        if path:
            self._source_var.set(path)

    def _on_source_mode_change(self, *_args) -> None:
        if self._source_mode.get() == "camera":
            self._source_var.set("0")
            self._browse_btn.configure(text="浏览...", state=tk.DISABLED)
        else:
            self._source_var.set("")
            self._browse_btn.configure(text="浏览...", state=tk.NORMAL)

    def _run(self) -> None:
        weights = self._weights_var.get().strip()
        source = self._source_var.get().strip()
        if not weights:
            messagebox.showwarning("缺少参数", "请选择权重文件")
            return
        if not source:
            source = "0" if self._source_mode.get() == "camera" else ""
        want_show = self._show_var.get()

        if want_show and self._source_mode.get() == "image" and not source.isdigit():
            # 图片/视频模式: 不让 CLI 弹窗(闪退), 推理完桌面端自己展示结果
            self._run_with_desktop_viewer(weights, source)
        else:
            # 摄像头模式: 直接传给 CLI (需要实时流)
            cmd = [sys.executable, "-m", "od_platform.cli.model_infer",
                   "--model", weights, "--source", source]
            if want_show:
                cmd.append("--show")
            run_in_thread(cmd, self.console)

    def _run_with_desktop_viewer(self, weights: str, source: str) -> None:
        """桌面端自己展示推理结果, 避免 CLI 弹窗闪退 + 窗口小。"""
        import glob as _glob
        # 记下推理前已有的 predict 目录
        before = set(_glob.glob(str(Path.cwd() / "runs" / "detect_infer" / "predict*")))
        self.console.clear()
        self.console.write(f"> 推理: {source}\n")
        self.console.write("─" * 60)

        def _target() -> None:
            import cv2 as _cv2
            try:
                env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                cmd = [sys.executable, "-m", "od_platform.cli.model_infer",
                       "--model", weights, "--source", source, "--save"]
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                for line in proc.stdout:
                    self.console.write(line.rstrip())
                proc.wait()
                if proc.returncode != 0:
                    self.console.write(f"\n✗ 退出码: {proc.returncode}")
                    return

                # 找到新产出的 predict 目录
                after = set(_glob.glob(str(Path.cwd() / "runs" / "detect_infer" / "predict*")))
                new_dirs = sorted(after - before)
                if not new_dirs:
                    self.console.write("\n未找到推理输出目录")
                    return
                out_dir = Path(new_dirs[-1])
                self.console.write(f"\n✓ 推理完成, 结果: {out_dir}")

                # 展示结果图
                images = sorted(out_dir.glob("*.jpg")) + sorted(out_dir.glob("*.png"))
                images = [p for p in images if not p.name.startswith("_")]
                if not images:
                    self.console.write("\n没有可展示的结果图")
                    return
                self.console.write(f"\n展示 {len(images)} 张结果图 (按任意键切换, Esc 退出)...")
                for img_path in images:
                    frame = _cv2.imread(str(img_path))
                    if frame is None:
                        continue
                    h, w = frame.shape[:2]
                    if h < 400 or w < 400:
                        scale = max(400 / h, 400 / w)
                        frame = _cv2.resize(frame, (int(w * scale), int(h * scale)))
                    _cv2.imshow("ODPlatform 推理结果 (任意键下一张 / Esc 退出)", frame)
                    key = _cv2.waitKey(0) & 0xFF
                    if key == 27:  # Esc
                        break
                _cv2.destroyAllWindows()
            except Exception as e:
                self.console.write(f"\n✗ 展示失败: {e}")

        threading.Thread(target=_target, daemon=True).start()


class SetupPage(ttk.Frame):
    """配置生成 —— 一键生成训练/评估/推理所需的运行时配置文件。"""

    _CONFIGS = [
        ("train", "训练配置 (train.yaml)", "模型训练所需的参数模板"),
        ("val", "评估配置 (val.yaml)", "模型评估所需的参数模板"),
        ("infer", "推理配置 (infer.yaml)", "模型推理所需的参数模板"),
    ]

    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        form = ttk.LabelFrame(self, text="一键生成运行时配置", padding=10)
        form.grid(row=0, column=0, sticky="ew")

        ttk.Label(form, text="以下配置文件首次使用前需生成, 之后可手动编辑参数。\n"
                  "已存在的不会被覆盖, 如需重生成请先删除旧文件。",
                  font=("", 9), foreground="gray").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self._check_vars = {}
        for i, (name, label, hint) in enumerate(self._CONFIGS, 1):
            var = tk.BooleanVar(value=True)
            self._check_vars[name] = var
            frame = ttk.Frame(form)
            frame.grid(row=i, column=0, columnspan=2, sticky="w", pady=1)
            ttk.Checkbutton(frame, text=label, variable=var).pack(side=tk.LEFT)
            ttk.Label(frame, text=f"  — {hint}", foreground="gray").pack(side=tk.LEFT)

        ttk.Button(form, text="▶ 生成选中配置", command=self._run).grid(
            row=len(self._CONFIGS) + 1, column=0, sticky="w", pady=(10, 0))

        self.console = ConsoleFrame(self)
        self.console.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

    def _run(self) -> None:
        selected = [n for n, v in self._check_vars.items() if v.get()]
        if not selected:
            messagebox.showinfo("提示", "请至少勾选一项配置")
            return
        # 逐个生成 (CLI 每次只接受一个参数)
        cmd = [sys.executable, "-m", "od_platform.runtime_config.generator"] + selected
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

        def _target() -> None:
            for name in selected:
                self.console.write(f"\n生成: {name}.yaml ...")
                try:
                    proc = subprocess.run(
                        [sys.executable, "-m", "od_platform.runtime_config.generator", name],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        env=env,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    )
                    self.console.write(proc.stdout.strip())
                    if proc.returncode != 0:
                        self.console.write(proc.stderr.strip())
                except Exception as e:
                    self.console.write(f"✗ 失败: {e}")
            self.console.write("\n✓ 配置生成完毕")

        threading.Thread(target=_target, daemon=True).start()


# ── 主窗口 ─────────────────────────────────────────────────────


class ODPlatformApp(tk.Tk):
    """ODPlatform 桌面端主窗口。"""

    def __init__(self):
        super().__init__()
        self.title("ODPlatform — 目标检测开发平台")
        self.geometry("900x680")
        self.minsize(800, 550)

        # ── 字体: 检测系统可用 CJK 字体, 优先微软雅黑 ──
        from tkinter import font as _tkfont
        _cjk_fonts = ["Microsoft YaHei", "SimHei", "Microsoft JhengHei", "SimSun", "KaiTi", "TkDefaultFont"]
        _available = set(_tkfont.families())
        self._cjk_font = next((f for f in _cjk_fonts if f in _available), "TkDefaultFont")
        self._cjk_mono = "Consolas" if "Consolas" in _available else self._cjk_font

        # 样式
        style = ttk.Style()
        available_themes = style.theme_names()
        if "clam" in available_themes:
            style.theme_use("clam")
        style.configure(".", font=(self._cjk_font, 9))
        style.configure("TLabel", font=(self._cjk_font, 9))
        style.configure("TButton", font=(self._cjk_font, 9))
        style.configure("TCheckbutton", font=(self._cjk_font, 9))
        style.configure("TRadiobutton", font=(self._cjk_font, 9))
        style.configure("TCombobox", font=(self._cjk_font, 9))
        style.configure("TLabelframe.Label", font=(self._cjk_font, 10, "bold"))

        # 顶部标题
        header = ttk.Frame(self, padding=(10, 8))
        header.pack(fill=tk.X)
        ttk.Label(header, text="ODPlatform 桌面端",
                  font=(self._cjk_font, 16, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text="目标检测一站式开发",
                  font=(self._cjk_font, 10)).pack(side=tk.LEFT, padx=(10, 0))

        # 标签页
        notebook = ttk.Notebook(self, padding=2)
        notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        notebook.add(TransformPage(notebook), text=" 数据转换 ")
        notebook.add(SetupPage(notebook), text=" 配置生成 ")
        notebook.add(ValidatePage(notebook), text=" 数据验证 ")
        notebook.add(TrainPage(notebook), text=" 模型训练 ")
        notebook.add(EvalPage(notebook), text=" 模型评估 ")
        notebook.add(InferPage(notebook), text=" 模型推理 ")

        # 底部状态栏
        footer = ttk.Frame(self, padding=(10, 2))
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        self._status_var = tk.StringVar(value="就绪")
        ttk.Label(footer, textvariable=self._status_var,
                  font=(self._cjk_font, 8)).pack(side=tk.LEFT)

        # 轮询日志队列
        self._poll_logs()

    def _poll_logs(self) -> None:
        """每 200ms 检查日志队列,有消息就弹到控制台。"""
        try:
            while True:
                msg = _log_queue.get_nowait()
                # 找到当前活动标签页的 ConsoleFrame 写入
                notebook = self.winfo_children()[1]  # Notebook
                current_tab = notebook.nametowidget(notebook.select())
                if hasattr(current_tab, "console"):
                    current_tab.console.write(msg)
        except queue.Empty:
            pass
        self.after(200, self._poll_logs)


def main() -> None:
    """桌面端入口。"""
    # 修复 Windows GBK 乱码: 控制台 + 子进程统一 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    _setup_logging()
    app = ODPlatformApp()
    app.mainloop()


if __name__ == "__main__":
    main()
