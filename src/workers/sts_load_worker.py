from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.services.sts_database import STSMigrationError
from src.services.sts_schema_upgrade_gate import upgrade_sts_file
from src.services.sts_store import STSStore

_log = logging.getLogger(__name__)


class STSLoadWorker(QObject):
    """STS dosyasını ana thread'i bloklamadan önce doğrular.

    KURAL: Bu worker hiçbir zaman STSStore, STSDatabase veya sqlite3.connect
    nesnesi ANA THREAD'E AKTARMAZ. SQLite connection thread'e bağlıdır;
    worker thread'de oluşturulan bir connection ana thread'de kullanılırsa
    ProgrammingError (check_same_thread=True default) veya veri bozulması olur.

    Worker dosya varlığı ve magic-bytes doğrulamasından sonra STSStore'u yalnızca
    kendi thread'inde açıp kapatarak migration hazırlığını tamamlar, ardından
    parametresiz finished() sinyali gönderir. Ana thread kendi STSStore
    bağlantısını _on_sts_load_finished() içinde yeniden oluşturur.
    """

    progress = Signal(int, str)
    # Sinyalde STSStore / bağlantı nesnesi YOK — sadece kontrol sonucu
    finished = Signal()
    failed = Signal(str)

    def __init__(self, path: Path):
        super().__init__()
        self.path = Path(path)

    def run(self):
        try:
            self.progress.emit(15, "STS dosyası doğrulanıyor...")
            if not self.path.exists():
                raise FileNotFoundError(f"Dosya bulunamadı: {self.path}")
            if not self.path.is_file():
                raise ValueError(f"Geçerli bir dosya değil: {self.path}")
            # Hafif ön-kontrol: SQLite magic bytes (connection açmadan)
            with open(self.path, "rb") as fh:
                header = fh.read(16)
            if not header.startswith(b"SQLite format 3"):
                raise ValueError("Dosya geçerli bir STS/SQLite veritabanı değil.")

            upgrade_result = upgrade_sts_file(
                self.path,
                progress_callback=lambda value, message: self.progress.emit(
                    value,
                    message,
                ),
            )
            if upgrade_result.status == "upgraded":
                _log.info(
                    "STS schema upgraded: path=%s from=%s to=%s migrations=%s backup=%s",
                    self.path,
                    upgrade_result.from_version,
                    upgrade_result.to_version,
                    upgrade_result.applied_migrations,
                    upgrade_result.backup_path,
                )
                backup_name = (
                    upgrade_result.backup_path.name
                    if upgrade_result.backup_path is not None
                    else "-"
                )
                self.progress.emit(
                    84,
                    f"Veri dosyası v{upgrade_result.from_version or 'legacy'} → "
                    f"v{upgrade_result.to_version} güncellendi. "
                    f"Yedek: {backup_name}",
                )

            self.progress.emit(88, "Güncel veri yapısı doğrulanıyor...")
            store = None
            try:
                store = STSStore(
                    self.path,
                    actor="Index Worker",
                    source="STS Index Worker",
                    actor_context={"actor_type": "SYSTEM", "actor_display_name": "Index Worker"},
                )
            finally:
                if store is not None:
                    store.db.close()
            self.progress.emit(92, "Doğrulama tamamlandı, yükleniyor...")
            self.finished.emit()
        except STSMigrationError as exc:
            _log.exception(
                "STSLoadWorker migration hatası: %s",
                getattr(exc, "technical_detail", ""),
            )
            backup_text = (
                f"\n\nYedek dosya: {exc.backup_path}"
                if getattr(exc, "backup_path", None)
                else ""
            )
            self.failed.emit(
                f"{exc.user_message}{backup_text}\n\nTeknik detaylar loga yazıldı."
            )
        except Exception as exc:
            _log.exception("STSLoadWorker doğrulama/hazırlık hatası")
            self.failed.emit(str(exc))
