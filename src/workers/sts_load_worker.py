from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

_log = logging.getLogger(__name__)


class STSLoadWorker(QObject):
    """STS dosyasını ana thread'i bloklamadan önce doğrular.

    KURAL: Bu worker hiçbir zaman STSStore, STSDatabase veya sqlite3.connect
    nesnesi ANA THREAD'E AKTARMAZ. SQLite connection thread'e bağlıdır;
    worker thread'de oluşturulan bir connection ana thread'de kullanılırsa
    ProgrammingError (check_same_thread=True default) veya veri bozulması olur.

    Worker yalnızca dosya varlığı ve magic-bytes doğrulaması yapar, ardından
    parametresiz finished() sinyali gönderir. Asıl STSStore ve contract index
    ana thread'de _on_sts_load_finished() içinde oluşturulur.
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
            self.progress.emit(80, "Doğrulama tamamlandı, yükleniyor...")
            self.finished.emit()
        except Exception as exc:
            _log.exception("STSLoadWorker doğrulama hatası")
            self.failed.emit(str(exc))

