"""Registro de procedencia de productos derivados: hashes de entradas, parámetros, versión y fecha."""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__


def hash_archivo(path: str | Path, bloque: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(bloque)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def hash_dict(d: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def escribir_procedencia(
    producto: str | Path,
    fuente: str,
    parametros: dict[str, Any] | None = None,
    entradas: list[str | Path] | None = None,
    extra: dict[str, Any] | None = None,
    hashear_entradas: bool = True,
) -> Path:
    """Escribe `<producto>.json` junto al producto con la información de procedencia."""
    producto = Path(producto)
    reg: dict[str, Any] = {
        "producto": producto.name,
        "fuente": fuente,
        "generado_utc": ahora_utc(),
        "version_codigo": __version__,
        "host": platform.node(),
        "parametros": parametros or {},
        "entradas": [],
    }
    for e in entradas or []:
        e = Path(e)
        item: dict[str, Any] = {"archivo": str(e)}
        if e.exists() and e.is_file():
            item["bytes"] = e.stat().st_size
            if hashear_entradas:
                item["sha256"] = hash_archivo(e)
        reg["entradas"].append(item)
    if producto.exists() and producto.is_file():
        reg["sha256_producto"] = hash_archivo(producto)
        reg["bytes_producto"] = producto.stat().st_size
    if extra:
        reg.update(extra)
    out = producto.with_suffix(producto.suffix + ".json") if producto.suffix != ".json" else producto
    with open(out, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False, default=str)
    return out


def leer_procedencia(producto: str | Path) -> dict[str, Any] | None:
    p = Path(producto)
    p = p.with_suffix(p.suffix + ".json")
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def producto_vigente(producto: str | Path, parametros: dict[str, Any]) -> bool:
    """True si el producto existe y su procedencia registra los mismos parámetros (hash)."""
    p = Path(producto)
    if not p.exists():
        return False
    reg = leer_procedencia(p)
    if not reg:
        return False
    return hash_dict(reg.get("parametros", {})) == hash_dict(parametros)
