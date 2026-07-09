"""Frame source registry — ``{source_type: SourceEntry}`` + ``@register_source`` decorator.

Pattern mirrors :mod:`od_platform.data_pipeline.convert.registry`.

Framework (this file + factory.py) never changes; adding a new source type = drop a
new ``.py`` in ``sources/`` and decorate its class/factory with ``@register_source``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .core.base import FrameSource

logger = logging.getLogger(__name__)

# A factory callable: (source_str, config, **kwargs) -> FrameSource
SourceFactory = Callable[..., FrameSource]


@dataclass(frozen=True)
class SourceEntry:
    """One row in the registry: a factory function and metadata."""

    factory: SourceFactory
    source_type: str
    description: str = ""


# Module-level singleton registry: {source_type_name → SourceEntry}
_REGISTRY: Dict[str, SourceEntry] = {}


def register_source(
    name: str,
    *,
    description: str = "",
):
    """Decorator: register a source factory under *name*.

    Usage::

        @register_source("camera", description="RGB / webcam capture")
        def _create_camera(source, config, **kwargs):
            ...
    """

    def decorator(func: SourceFactory) -> SourceFactory:
        if name in _REGISTRY:
            logger.warning("Source type %r re-registered; latter overwrites former.", name)
        _REGISTRY[name] = SourceEntry(
            factory=func,
            source_type=name,
            description=description,
        )
        return func

    return decorator


def get_source(name: str) -> SourceEntry:
    """Look up a source entry by name.  Triggers lazy auto-discovery on first call.

    Raises:
        ValueError: *name* is not registered.
    """
    _lazy_init()
    if name not in _REGISTRY:
        raise ValueError(
            f"Unregistered source type: {name!r}. "
            f"Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def available_sources() -> List[str]:
    """Return sorted list of all registered source type names."""
    _lazy_init()
    return sorted(_REGISTRY)


# ── lazy auto-discovery ──────────────────────────────────────────────
_LAZY_INITIALIZED = False


def _lazy_init() -> None:
    """Scan ``sources/`` subpackage, import every non-private module so
    ``@register_source`` decorators fire."""
    global _LAZY_INITIALIZED
    if _LAZY_INITIALIZED:
        return

    from . import sources as _sources_pkg
    from od_platform.common.registry_utils import import_submodules

    import_submodules(_sources_pkg)
    _LAZY_INITIALIZED = True
