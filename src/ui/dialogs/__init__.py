from __future__ import annotations

# Tahmini Teslimat Takvimi Excel dilimleyicilerini, temel rapor dosyasını
# riske atmadan ikinci ve bağımsız bir Excel COM oturumunda kurar.
try:
    from src.services.delivery_schedule_slicer_runtime_fix import (
        install_delivery_schedule_slicer_fix,
    )

    install_delivery_schedule_slicer_fix()
except Exception:
    # Dialog paketinin yüklenmesi hiçbir zaman bu uyumluluk katmanına bağlı
    # olmamalıdır. Ayrıntılı hata, rapor oluşturma sırasında kullanıcıya döner.
    pass
