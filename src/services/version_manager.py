from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

VERSION_PREFIX = "STS_v"
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_MAX_BUILD = 9


def versioned_workbook_path(path: Path, version: str) -> Path:
    """Excel dosya adını doğrudan sürüm adına çevirir: STS_vA1.xlsx."""
    p = Path(path)
    return p.with_name(f"{version}{p.suffix}")


def save_store_as_versioned_file(store, new_version: str) -> Path:
    """
    Workbook'u sürüm ekli dosya adına kaydeder ve store.path'i günceller.
    Eski dosya farklı addaysa, başarılı kayıt sonrası eski kopya silinmeye çalışılır.
    """
    old_path = Path(store.path)
    new_path = versioned_workbook_path(old_path, new_version)
    if old_path == new_path:
        store.save()
        return new_path

    old_exists = old_path.exists()
    store.path = new_path
    try:
        store.save()
    except Exception:
        store.path = old_path
        raise

    if old_exists:
        try:
            old_path.unlink()
        except Exception:
            pass
    return new_path


def parse_version(version_str: str) -> Optional[Tuple[int, int]]:
    """
    "STS_vA1" → (0, 1)   (letter_idx, build)
    "STS_vB3" → (1, 3)
    Geçersiz → None
    """
    if not version_str:
        return None
    m = re.match(r"^STS_v([A-Z])([1-9])$", str(version_str or "").strip())
    if not m:
        return None
    letter_idx = _LETTERS.index(m.group(1))
    build = int(m.group(2))
    return (letter_idx, build)


def format_version(letter_idx: int, build: int) -> str:
    """(0, 1) → "STS_vA1" """
    letter_idx = letter_idx % len(_LETTERS)
    build = max(1, min(_MAX_BUILD, build))
    return f"{VERSION_PREFIX}{_LETTERS[letter_idx]}{build}"


def increment_version(current: Optional[str]) -> str:
    """
    Mevcut versiyonu bir artırır.
    None veya geçersiz → "STS_vA1"
    "STS_vA9" → "STS_vB1"
    "STS_vZ9" → "STS_vA1"  (döngüsel)
    """
    parsed = parse_version(current or "")
    if parsed is None:
        return format_version(0, 1)
    letter_idx, build = parsed
    if build >= _MAX_BUILD:
        return format_version((letter_idx + 1) % len(_LETTERS), 1)
    return format_version(letter_idx, build + 1)


def read_version(store) -> Optional[str]:
    """
    ExcelStore'dan mevcut versiyonu okur.
    _Meta sayfasından "version" anahtarını döndürür.
    Sayfa/hücre yoksa None.
    """
    try:
        wb = store.wb
        if "_Meta" not in wb.sheetnames:
            return None
        ws = wb["_Meta"]
        for row in ws.iter_rows(min_row=1, max_col=2, values_only=True):
            if row and str(row[0] or "").strip().lower() == "version":
                return str(row[1] or "").strip() or None
    except Exception:
        pass
    return None


def write_version(store, new_version: str, actor: Optional[str] = None) -> None:
    """
    ExcelStore'a yeni versiyonu yazar.
    _Meta sayfası yoksa oluşturur (gizli sayfa).
    Yazılan alanlar:
      version         → "STS_vA1"
      version_date    → "2025-05-11 14:32:07"
      version_actor   → "PC4166_BD26"
    """
    try:
        wb = store.wb
        if "_Meta" not in wb.sheetnames:
            ws = wb.create_sheet("_Meta")
            ws.sheet_state = "hidden"
        else:
            ws = wb["_Meta"]

        _actor = str(actor or "").strip() or _default_actor()
        _now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Mevcut satırları tara, varsa güncelle
        meta = {
            "version": new_version,
            "version_date": _now,
            "version_actor": _actor,
        }
        existing_keys = {}
        for i, row in enumerate(ws.iter_rows(min_row=1, max_col=2), start=1):
            key = str(row[0].value or "").strip().lower() if row[0] else ""
            if key in meta:
                existing_keys[key] = i

        for key, value in meta.items():
            if key in existing_keys:
                ws.cell(existing_keys[key], 2, value)
            else:
                ws.append([key, value])

    except Exception:
        pass


def bump_version(store, actor: Optional[str] = None) -> str:
    """
    Tek çağrıyla: oku → artır → yaz.
    Yeni versiyonu döndürür.
    save() ÇAĞRILMAZ — çağıran yapar.
    """
    current = read_version(store)
    new_ver = increment_version(current)
    write_version(store, new_ver, actor=actor)
    return new_ver


def _default_actor() -> str:
    try:
        import getpass
        import socket
        return f"{socket.gethostname()}_{getpass.getuser()}"
    except Exception:
        return "Bilinmiyor"
