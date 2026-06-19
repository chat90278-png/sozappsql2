"""Domain-level constants shared across UI and Excel layers."""

CORE_SHEETS = [
    "ANASAYFA",
    "VeriÇekme",
    "Sistem Bileşenleri",
    "Kullanıcılar",
    "_Data",
    "_Lists",
    "Etiketler",
    "Config",
    "Değişiklik Kayıtları",
]

HEADER_ROW = 4
SUBHEADER_ROW = 5
DATA_START_ROW = 6

MAIN_COLUMN_HEADERS = [
    "Sözleşme Adı / Kontrat No",
    "Kullanıcı",
    "Yİ/YD",
    "Sözleşme Tipi",
    "Faaliyetler",
    "Teslimat",
    "Sözleşme İçeriği",
    "Sözleşmenin İmzalandığı Tarih",
    "T0 Başlangıç Tarihi",
    "T0+Ay",
    "Termin Tarihi",
    "Durum",
    "Gerçek Teslimat",
    "Not",
]

STATUS_VALUES = ["Başlanmadı", "Teslimata Hazırlanıyor", "Parçalı Teslimat", "Teslim Edildi"]
