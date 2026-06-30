from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.services.sts_database import STSMigrationError
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
            self.progress.emit(55, "Veritabanı hazırlanıyor...")
            store = None
            try:
                store = STSStore(self.path, actor="Index Worker", source="STS Index Worker")
            finally:
                if store is not None:
                    store.db.close()
            self.progress.emit(80, "Doğrulama tamamlandı, yükleniyor...")
            self.finished.emit()
        except STSMigrationError as exc:
            _log.exception("STSLoadWorker migration hatası: %s", getattr(exc, "technical_detail", ""))
            backup_text = f"\n\nYedek dosya: {exc.backup_path}" if getattr(exc, "backup_path", None) else ""
            self.failed.emit(f"{exc.user_message}{backup_text}\n\nTeknik detaylar loga yazıldı.")
        except Exception as exc:
            _log.exception("STSLoadWorker doğrulama/hazırlık hatası")
            self.failed.emit(str(exc))

