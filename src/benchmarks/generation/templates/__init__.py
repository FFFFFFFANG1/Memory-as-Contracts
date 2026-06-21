from __future__ import annotations

from importlib import resources

TEMPLATE_PACKAGE = __name__


def load_template(name: str, *, version: str = "v1") -> str:
    filename = f"{name}.{version}.txt"
    try:
        return resources.files(TEMPLATE_PACKAGE).joinpath(filename).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"unknown generation template {filename!r}") from exc


__all__ = ["load_template"]
