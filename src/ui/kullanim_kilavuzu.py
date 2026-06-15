from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.message_boxes import show_warning

GUIDE_IMAGE_DIR = Path(__file__).resolve().parent / "assets" / "guide_screens"
GUIDE_SCREENSHOT_TARGET_SIZE = QSize(1280, 700)
GUIDE_IMAGE_PADDING = 32
COMPREHENSIVE_GUIDE_PDF = "STS_KullanmaKılavuzu.pdf"


def app_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if sys.argv and sys.argv[0]:
        return Path(sys.argv[0]).resolve().parent
    return Path.cwd()

GUIDE_SECTIONS = [
    {
        "title": "Ana Ekran",
        "icon": "🏠",
        "image": "ana_ekran.png",
        "purpose": "STS'in ana çalışma alanıdır. Sözleşmeleri tek tabloda izlemek, aramak, filtrelemek ve yeni kayıt akışlarını başlatmak için kullanılır.",
        "actions": [
            "Excel bağlantı durumunu üst çubuktan takip edebilirsiniz.",
            "Sözleşme listesinde Tür, No, Kullanıcı, Durum, Termin, Kalan Gün, Etiket ve Özet sütunlarını görebilirsiniz.",
            "Arama kutusu ile sözleşme no, kullanıcı veya durum metnine göre hızlı filtreleme yapabilirsiniz.",
            "Sütun başlıklarındaki filtrelerden Excel benzeri çoklu değer seçimi yapabilirsiniz.",
            "Satıra çift tıklayarak sözleşme detay ekranını açabilirsiniz.",
            "☰ Menü üzerinden Excel dosyası, kullanıcı, platform, etiket ve bileşen yönetimlerine ulaşabilirsiniz.",
            "+ Yeni Sözleşme ile yeni sözleşme oluşturma akışını başlatabilirsiniz.",
            "Filtreleri Temizle ile hem arama kutusunu hem de sütun filtrelerini sıfırlayabilirsiniz.",
        ],
        "tip": "Büyük Excel dosyalarında ilk indeksleme bitene kadar üst çubuktaki bağlantı durumunu kontrol edin.",
    },
    {
        "title": "Yeni Sözleşme Ekleme",
        "icon": "➕",
        "parent": "Ana Ekran",
        "image": "yeni_sozlesme_ekleme.png",
        "purpose": "Ana ekrandaki + Yeni Sözleşme akışıyla ana sözleşme veya ihtiyaç duyulan yeni kayıtları standart alanlarla oluşturmak için kullanılır.",
        "actions": [
            "+ Yeni Sözleşme butonuyla kayıt penceresini açabilirsiniz.",
            "Sözleşme türü, sözleşme no, kullanıcı, durum, başlangıç/termin tarihleri ve açıklama gibi zorunlu alanları doldurabilirsiniz.",
            "Kullanıcı ve platform seçimlerini yönetim ekranlarında tanımlanan listelerden seçebilirsiniz.",
            "Kaydet/Oluştur butonuyla yeni sözleşmeyi Excel dosyasına ekleyebilir, İptal/Kapat ile kayıt oluşturmadan çıkabilirsiniz.",
            "Kayıt sonrası ana listedeki arama ve filtreleri kullanarak yeni sözleşmeyi kontrol edebilirsiniz.",
        ],
        "tip": "Kaydetmeden önce sözleşme no ve tarih alanlarını kontrol etmek, sonraki SD ve sistem kayıtlarının doğru bağlanmasını sağlar.",
    },
    {
        "title": "Platform Yönetimi",
        "icon": "🧭",
        "parent": "Ana Ekran",
        "image": "platform_yonetimi.png",
        "purpose": "☰ Menü altından açılan platform tanımlarını yönetir; sözleşmelerde ve raporlamada kullanılan platform listesini güncel tutmak için kullanılır.",
        "actions": [
            "☰ Menü → Platform Yönetimi yoluyla pencereyi açabilirsiniz.",
            "+ Platform Ekle ile yeni platform adı, kısa ad/açıklama ve varsa logo bilgisini ekleyebilirsiniz.",
            "Seçili platformu Düzenle butonuyla güncelleyebilir, Sil butonuyla kullanılmayan tanımı kaldırabilirsiniz.",
            "Logo seç/değiştir alanı varsa platform kartlarında kullanılacak görseli güncelleyebilirsiniz.",
            "Kaydet/Tamam ile değişiklikleri uygulayabilir, İptal/Kapat ile pencereyi kapatabilirsiniz.",
        ],
        "tip": "Platform adlarını tekilleştirmeniz filtrelerde ve özet ekranlarında dağınık kayıt oluşmasını önler.",
    },
    {
        "title": "Kullanıcı Yönetimi",
        "icon": "👤",
        "parent": "Ana Ekran",
        "image": "kullanici_yonetimi.png",
        "purpose": "Sözleşme kayıtlarında seçilecek kullanıcı/kurum listesini yönetmek ve pasif kullanıcıların yeni kayıtlarda yanlışlıkla seçilmesini önlemek için kullanılır.",
        "actions": [
            "☰ Menü → Kullanıcı Yönetimi yoluyla kullanıcı listesini açabilirsiniz.",
            "+ Kullanıcı Ekle ile yeni kullanıcı/kurum adı oluşturabilirsiniz.",
            "Düzenle ile seçili kaydın adını veya açıklamasını güncelleyebilirsiniz.",
            "Aktif/Pasif durumunu değiştirerek kullanıcının yeni kayıt seçimlerinde görünüp görünmeyeceğini belirleyebilirsiniz.",
            "Sil butonuyla kullanılmayan kullanıcıyı kaldırabilir, Kaydet/Tamam ile değişiklikleri uygulayabilirsiniz.",
        ],
        "tip": "Geçmiş sözleşmelerde kullanılan kullanıcıları silmek yerine pasife almak rapor tutarlılığı açısından daha güvenlidir.",
    },
    {
        "title": "Etiket Yönetimi",
        "icon": "🏷",
        "parent": "Ana Ekran",
        "image": "etiket_yonetimi.png",
        "purpose": "Sözleşmeleri renkli etiketlerle sınıflandırmak için kullanılacak etiket adlarını ve renklerini tanımlar.",
        "actions": [
            "☰ Menü → Etiket Yönetimi yoluyla etiket listesini açabilirsiniz.",
            "+ Etiket Ekle ile etiket adı ve renk seçimi yapabilirsiniz.",
            "Düzenle ile etiket adını veya rengini değiştirebilirsiniz.",
            "Sil/Kaldır ile kullanılmayan etiketi listeden çıkarabilirsiniz.",
            "Kaydet/Tamam sonrasında etiketler ana liste ve sözleşme detayındaki etiket atama alanlarında kullanılabilir.",
        ],
        "tip": "Az sayıda ve anlamı net renk kullanmak ana listede öncelikleri daha hızlı fark etmenizi sağlar.",
    },
    {
        "title": "Bileşen Yönetimi",
        "icon": "🧱",
        "parent": "Ana Ekran",
        "image": "bilesen_yonetimi.png",
        "purpose": "Sistem kayıtlarında kullanılacak bileşen kalemlerini standartlaştırır ve teslimat/kabul miktarlarının aynı adlarla takip edilmesini sağlar.",
        "actions": [
            "☰ Menü → Bileşen Yönetimi yoluyla bileşen tanımlarını açabilirsiniz.",
            "+ Bileşen Ekle ile yeni bileşen adı ve gerekirse açıklama/birim bilgisi ekleyebilirsiniz.",
            "Düzenle ile bileşen adını güncelleyebilir, Sil ile kullanılmayan tanımı kaldırabilirsiniz.",
            "Kaydet/Tamam ile listeyi güncelleyip sistem ekleme/düzenleme ekranlarında kullanılabilir hale getirebilirsiniz.",
            "Kapat/İptal ile değişiklik yapmadan çıkabilirsiniz.",
        ],
        "tip": "Aynı bileşen için farklı yazımlar kullanmamak özet ekranındaki teslim edilecek/teslim edilen/kalan hesaplarını daha okunur yapar.",
    },
    {
        "title": "Sözleşme Detay Ekranı",
        "icon": "📄",
        "image": "sozlesme_detay.png",
        "purpose": "Seçilen sözleşmenin tüm meta bilgilerini, etiketlerini, sistemlerini ve teslimat/kabul kayıtlarını düzenlemek için kullanılır.",
        "actions": [
            "Ana Bilgileri Düzenle ile sözleşme türü, kullanıcı, durum ve tarih alanlarını güncelleyebilirsiniz.",
            "Etiket Yönetimi ile sözleşmeye renkli etiket ekleyebilir veya mevcut etiketi kaldırabilirsiniz.",
            "Sistem Yönetimi bölümünde sistem ekleme, düzenleme, silme ve çoğaltma işlemlerini yapabilirsiniz.",
            "Teslimat/Kabul alanında manuel kabul ekleyebilir veya sistem bilgisine göre otomatik kabul üretebilirsiniz.",
            "Alt sözleşme ilişkilerini takip ederek ana sözleşme ile SD kayıtları arasında geçiş yapabilirsiniz.",
            "Kaydet butonu ile yaptığınız değişiklikleri Excel dosyasına yazabilirsiniz.",
        ],
        "tip": "Değişiklikleri tamamladıktan sonra pencereyi kapatmadan önce Kaydet butonunu kullanmayı unutmayın.",
    },
    {
        "title": "SD Ekleme",
        "icon": "📎",
        "parent": "Sözleşme Detay Ekranı",
        "image": "sd_ekleme.png",
        "purpose": "Açık olan ana sözleşmeye bağlı alt sözleşme/SD kaydı oluşturmak ve ana sözleşme ailesi altında birlikte takip etmek için kullanılır.",
        "actions": [
            "Sözleşme detay ekranındaki SD/Alt Sözleşme Ekle butonuyla yeni SD penceresini açabilirsiniz.",
            "SD numarası, kullanıcı, durum, başlangıç/termin tarihi ve açıklama alanlarını doldurabilirsiniz.",
            "Ana sözleşme bağlantısı otomatik korunur; böylece özet ekranında aile kapsamı birlikte görülebilir.",
            "Kaydet/Oluştur ile SD kaydını ekleyebilir, İptal/Kapat ile işlemden vazgeçebilirsiniz.",
            "Kayıt sonrası alt sözleşme listesi veya bağlantı alanından SD kaydına geçiş yapabilirsiniz.",
        ],
        "tip": "SD numarasını ana sözleşme numarasıyla tutarlı yazmanız arama ve aile takibini kolaylaştırır.",
    },
    {
        "title": "Sistem Ekleme ve Düzenleme",
        "icon": "🧩",
        "parent": "Sözleşme Detay Ekranı",
        "image": "sistem_ekleme_duzenleme.png",
        "purpose": "Sözleşmeye bağlı sistemleri, sistem durumlarını, termin/kabul bilgilerini ve sistem bileşen miktarlarını yönetir.",
        "actions": [
            "Sistem Yönetimi bölümündeki Yeni Sistem Ekle butonuyla yeni sistem kaydı oluşturabilirsiniz.",
            "Düzenle butonuyla seçili sistemin adı, durum, termin, kabul tarihi ve açıklama alanlarını güncelleyebilirsiniz.",
            "Bileşen satırlarında teslim edilecek miktarları girerek teslimat/kabul takibini hazırlayabilirsiniz.",
            "Çoğalt/Kopyala butonuyla benzer sistemleri hızlıca oluşturabilir, Sil butonuyla hatalı sistemi kaldırabilirsiniz.",
            "Kaydet/Tamam ile sistem değişikliklerini sözleşme detayına aktarabilirsiniz.",
        ],
        "tip": "Sistem adı, durum ve bileşen miktarlarını kaydetmeden önce kontrol etmek özet metriklerinin doğru hesaplanmasını sağlar.",
    },
    {
        "title": "Kabul Ekleme",
        "icon": "✅",
        "parent": "Sözleşme Detay Ekranı",
        "image": "kabul_ekleme.png",
        "purpose": "Teslim edilen sistem veya bileşenler için manuel kabul kaydı oluşturmak ya da sistem bilgilerine göre kabul sürecini güncellemek için kullanılır.",
        "actions": [
            "Teslimat/Kabul alanındaki Kabul Ekle veya Manuel Kabul Ekle butonuyla kayıt penceresini açabilirsiniz.",
            "Kabul tarihi, kabul no/tutanak bilgisi, ilgili sistem ve açıklama alanlarını doldurabilirsiniz.",
            "Bileşen bazlı miktar girilebiliyorsa teslim edilen miktarları ilgili satırlara yazabilirsiniz.",
            "Kaydet/Ekle ile kabul kaydını listeye ekleyebilir, İptal/Kapat ile vazgeçebilirsiniz.",
            "Kabul sonrası sistem durumu ve kalan bileşen miktarlarını detay/özet ekranlarından kontrol edebilirsiniz.",
        ],
        "tip": "Kabul tarihini ve miktarları doğru girmek, gecikme ve kalan teslimat uyarılarının doğru çalışmasını sağlar.",
    },
    {
        "title": "Sözleşme Silme",
        "icon": "🗑",
        "parent": "Sözleşme Detay Ekranı",
        "image": "sozlesme_silme.png",
        "purpose": "Hatalı veya artık takip edilmeyecek sözleşme kayıtlarını kontrollü şekilde kaldırmak için kullanılır.",
        "actions": [
            "Sözleşme detay ekranındaki Sil/Sözleşmeyi Sil butonuyla silme işlemini başlatabilirsiniz.",
            "Açılan onay mesajında silinecek sözleşme numarasını ve varsa bağlı alt kayıtları kontrol edebilirsiniz.",
            "Evet/Sil ile işlemi onaylayabilir, Hayır/İptal ile kaydı koruyabilirsiniz.",
            "Silme sonrası ana listeye dönerek kaydın listeden kalktığını ve filtrelerin güncel olduğunu kontrol edebilirsiniz.",
        ],
        "tip": "Silme işlemi geri alınamayabileceği için işlemden önce Excel dosyasının güncel yedeğinin bulunduğundan emin olun.",
    },
    {
        "title": "Sözleşme Bilgileri Düzenle",
        "icon": "✏️",
        "parent": "Sözleşme Detay Ekranı",
        "image": "sozlesme_bilgileri_duzenle.png",
        "purpose": "Mevcut sözleşmenin tür, kullanıcı, durum, tarih ve açıklama gibi ana bilgilerini güncellemek için kullanılır.",
        "actions": [
            "Ana Bilgileri Düzenle butonuyla düzenleme penceresini açabilirsiniz.",
            "Sözleşme türü, kullanıcı, durum, başlangıç tarihi, termin tarihi ve açıklama alanlarını güncelleyebilirsiniz.",
            "Tarih alanlarını takvim seçiciyle düzenleyerek yanlış format riskini azaltabilirsiniz.",
            "Kaydet/Tamam ile değişiklikleri detay ekranına aktarabilir, İptal/Kapat ile eski bilgileri koruyabilirsiniz.",
            "Detay ekranındaki ana Kaydet butonuyla değişiklikleri Excel dosyasına yazmayı unutmayın.",
        ],
        "tip": "Termin veya durum değişiklikleri takvim ve özet ekranlarını etkilediği için güncelleme sonrası bu ekranları kontrol edin.",
    },
    {
        "title": "Etiket Atama",
        "icon": "🏷️",
        "parent": "Sözleşme Detay Ekranı",
        "image": "etiket_atama.png",
        "purpose": "Sözleşmeye öncelik, kategori veya takip notu anlamı taşıyan renkli etiketleri bağlamak ya da mevcut etiketi kaldırmak için kullanılır.",
        "actions": [
            "Etiket Yönetimi/Etiket Ata butonuyla etiket seçim alanını açabilirsiniz.",
            "Listeden daha önce tanımlanan renkli etiketi seçerek sözleşmeye atayabilirsiniz.",
            "Etiketi Kaldır/Temizle butonuyla sözleşmedeki mevcut etiketi silebilirsiniz.",
            "Yeni bir etiket gerekiyorsa önce ana ekrandaki ☰ Menü → Etiket Yönetimi bölümünde etiketi oluşturabilirsiniz.",
            "Kaydet/Tamam ile atamayı uygulayıp detay ekranındaki ana Kaydet butonuyla Excel'e yazabilirsiniz.",
        ],
        "tip": "Etiketleri aciliyet veya takip sorumluluğu gibi net anlamlarla kullanmak ana listede hızlı önceliklendirme sağlar.",
    },
    {
        "title": "Takvim Ekranı",
        "icon": "🗓",
        "image": "takvim.png",
        "purpose": "Sözleşme ve sistem terminlerini aylık takvim görünümünde izlemek, geciken veya yaklaşan işleri görsel olarak fark etmek için kullanılır.",
        "actions": [
            "Sözleşme/Sistem modu arasında geçiş yaparak takvimde hangi terminlerin gösterileceğini belirleyebilirsiniz.",
            "‹ ve › kontrolleriyle aylar arasında gezinebilir, Bugün ile güncel aya dönebilirsiniz.",
            "Geciken, kritik veya yaklaşan terminleri renk ve uyarı simgeleriyle takip edebilirsiniz.",
            "Takvimdeki kayıtları inceleyerek ilgili sözleşme veya sistem için aksiyon planlayabilirsiniz.",
        ],
        "tip": "⚠ ve ⏳ işaretleri gecikme veya 60 gün içinde dolacak termin risklerini hızlıca fark etmenizi sağlar.",
    },
    {
        "title": "Özet Ekranı",
        "icon": "📊",
        "image": "ozet.png",
        "purpose": "Seçilen sözleşme ailesinin durumunu, sistem sayılarını, teslimat/kabul metriklerini ve bileşen durumunu tek ekranda özetler.",
        "actions": [
            "Ana sözleşme ve alt sözleşme kapsamını Tür alanından daraltabilir veya tüm aileyi birlikte inceleyebilirsiniz.",
            "Sözleşmeler/Sistem Bilgisi panelinden durum, termin, kabul tarihi ve sistem sayılarını kontrol edebilirsiniz.",
            "Bileşen Durumu panelinde teslim edilecek, teslim edilen ve kalan bileşen miktarlarını görebilirsiniz.",
            "Üst metrik kartları ile toplam sistem, kabul ve durum dağılımlarını hızlıca okuyabilirsiniz.",
        ],
        "tip": "Özet ekranı geniş tablolar için yatay alanı artırılmış şekilde açılır; yine de uzun metinlerde pencereyi büyütebilirsiniz.",
    },
]


class GuideImage(QLabel):
    def __init__(self, image_name: str, title: str, parent=None):
        super().__init__(parent)
        self.image_name = image_name
        self.title = title
        self.image_path = GUIDE_IMAGE_DIR / image_name
        self._loaded_size = QSize()
        self._last_target_size = QSize()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(380)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setObjectName("guideImage")
        self.setWordWrap(True)
        self._set_placeholder()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pixmap() and self._loaded_size.isValid():
            target_size = self._target_size()
            if (
                abs(target_size.width() - self._last_target_size.width()) > 24
                or abs(target_size.height() - self._last_target_size.height()) > 24
            ):
                QTimer.singleShot(0, self.load_image)

    def _target_size(self) -> QSize:
        available_width = max(320, self.width() - GUIDE_IMAGE_PADDING)
        return GUIDE_SCREENSHOT_TARGET_SIZE.scaled(
            QSize(min(available_width, GUIDE_SCREENSHOT_TARGET_SIZE.width()), GUIDE_SCREENSHOT_TARGET_SIZE.height()),
            Qt.KeepAspectRatio,
        )

    def load_image(self):
        """Load the guide screenshot lazily and scaled to the visible area.

        The dialog no longer decodes every full-size screenshot while opening.
        This avoids the white-screen delay and native Qt image crashes that can
        happen with very large or invalid screenshot files in packaged builds.
        """
        if not self.image_path.exists():
            self._set_placeholder()
            return

        target_size = self._target_size()
        reader = QImageReader(str(self.image_path))
        reader.setAutoTransform(True)

        original_size = reader.size()
        if original_size.isValid() and original_size.width() > 0 and original_size.height() > 0:
            target_size = original_size.scaled(target_size, Qt.KeepAspectRatio)
            reader.setScaledSize(target_size)

        image = reader.read()
        if image.isNull():
            error = reader.errorString() or "Görsel okunamadı."
            self._set_placeholder(f"{self.title} görseli yüklenemedi.\n\n{error}\n\nDosya: {self.image_name}")
            return

        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self._set_placeholder(f"{self.title} görseli yüklenemedi.\n\nDosya: {self.image_name}")
            return

        self.setText("")
        self.setPixmap(pixmap)
        self._loaded_size = pixmap.size()
        self._last_target_size = target_size
        self.setFixedHeight(pixmap.height() + GUIDE_IMAGE_PADDING)

    def _set_placeholder(self, message: str | None = None):
        self.clear()
        self._loaded_size = QSize()
        self._last_target_size = QSize()
        self.setFixedHeight(430)
        self.setText(
            message
            or (
                f"{self.title} görseli henüz eklenmedi.\n\n"
                f"Beklenen dosya: src/ui/assets/guide_screens/{self.image_name}\n"
                "Öneri: 1920×1050 ekran görüntüsünü 1280×700 PNG olarak yükleyin."
            )
        )



class UsageGuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kullanım Kılavuzu")
        self.resize(1620, 920)
        self.setMinimumSize(1180, 760)
        self.setStyleSheet(self._style())

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        header = self._build_header()
        root.addWidget(header)

        content = QHBoxLayout()
        content.setSpacing(12)
        root.addLayout(content, 1)

        self.nav = QListWidget()
        self.nav.setObjectName("guideNav")
        self.nav.setFixedWidth(310)
        for section in GUIDE_SECTIONS:
            prefix = "   ↳ " if section.get("parent") else ""
            item = QListWidgetItem(f"{prefix}{section['icon']}  {section['title']}")
            item.setSizeHint(item.sizeHint().expandedTo(item.sizeHint()))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._set_page)
        content.addWidget(self.nav)

        self.stack = QStackedWidget()
        self.stack.setObjectName("guideStack")
        for section in GUIDE_SECTIONS:
            self.stack.addWidget(self._build_page(section))
        content.addWidget(self.stack, 1)

        foot = QHBoxLayout()
        foot.addWidget(self._build_icon_dictionary(), 1)
        close_btn = QPushButton("Kapat")
        close_btn.setObjectName("primaryButton")
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn, 0, Qt.AlignRight)
        root.addLayout(foot)

        self.nav.setCurrentRow(0)

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("guideHero")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(16)

        text_lay = QVBoxLayout()
        text_lay.setContentsMargins(0, 0, 0, 0)
        text_lay.setSpacing(6)

        title = QLabel("📘 STS Kullanım Kılavuzu")
        title.setObjectName("guideHeroTitle")
        subtitle = QLabel(
            "Ekran bazlı hızlı anlatım: hangi ekran ne işe yarar, o ekranda neler yapılabilir ve hangi görsel dosyası kullanılmalıdır."
        )
        subtitle.setObjectName("guideHeroSubtitle")
        subtitle.setWordWrap(True)
        text_lay.addWidget(title)
        text_lay.addWidget(subtitle)
        lay.addLayout(text_lay, 1)

        pdf_btn = QPushButton("📄 Kapsamlı PDF Kılavuzu")
        pdf_btn.setObjectName("guidePdfButton")
        pdf_btn.setToolTip(f"Uygulama klasöründeki {COMPREHENSIVE_GUIDE_PDF} dosyasını aç")
        pdf_btn.clicked.connect(self.open_comprehensive_pdf_guide)
        lay.addWidget(pdf_btn, 0, Qt.AlignTop | Qt.AlignRight)
        return frame

    def open_comprehensive_pdf_guide(self):
        pdf_path = app_folder() / COMPREHENSIVE_GUIDE_PDF
        if not pdf_path.is_file():
            show_warning(
                self,
                "Kapsamlı Kullanma Kılavuzu",
                f"{COMPREHENSIVE_GUIDE_PDF} dosyası uygulama klasöründe bulunamadı.\n\nAranan klasör:\n{app_folder()}",
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path))):
            show_warning(
                self,
                "Kapsamlı Kullanma Kılavuzu",
                f"PDF dosyası açılamadı:\n{pdf_path}",
            )


    def _build_page(self, section: dict) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        if section.get("parent"):
            parent = QLabel(f"{section['parent']} alt sayfası")
            parent.setObjectName("guideParentTitle")
            lay.addWidget(parent)

        title = QLabel(f"{section['icon']} {section['title']}")
        title.setObjectName("guidePageTitle")
        lay.addWidget(title)

        image = GuideImage(section["image"], section["title"])
        lay.addWidget(image)

        purpose = self._info_card("Ne işe yarar?", [section["purpose"]], "purposeCard")
        lay.addWidget(purpose)

        actions = self._info_card("Bu ekranda neler yapılabilir?", section["actions"], "actionsCard", bullet=True)
        lay.addWidget(actions)

        tip = self._info_card("İpucu / Dikkat", [section["tip"]], "tipCard")
        lay.addWidget(tip)

        lay.addStretch(1)
        scroll.setWidget(page)
        return scroll

    def _info_card(self, title: str, lines: list[str], object_name: str, bullet: bool = False) -> QFrame:
        frame = QFrame()
        frame.setObjectName(object_name)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(7)

        title_label = QLabel(title)
        title_label.setObjectName("guideCardTitle")
        lay.addWidget(title_label)

        for line in lines:
            label = QLabel(("• " if bullet else "") + line)
            label.setObjectName("guideCardText")
            label.setWordWrap(True)
            lay.addWidget(label)
        return frame

    def _build_icon_dictionary(self) -> QWidget:
        """Backward-compatible no-op for builds that still call the old footer.

        The visible Simge Sözlüğü section was intentionally removed, but adding
        this hidden placeholder prevents mixed/stale deployments from crashing
        with AttributeError while the new footer code is rolled out.
        """
        placeholder = QWidget()
        placeholder.setVisible(False)
        return placeholder


    def showEvent(self, event):
        super().showEvent(event)
        self._load_current_images()

    def _set_page(self, index: int):
        if index >= 0:
            self.stack.setCurrentIndex(index)
            QTimer.singleShot(0, self._load_current_images)

    def _load_current_images(self):
        page = self.stack.currentWidget()
        if not page:
            return
        for image in page.findChildren(GuideImage):
            image.load_image()

    def _style(self) -> str:
        return """
            QDialog { background:#eef3f8; }
            QLabel { font-family:'Segoe UI', Arial; color:#0f172a; background:transparent; }
            QFrame#guideHero { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1d4ed8, stop:1 #0ea5e9); border-radius:16px; }
            QLabel#guideHeroTitle { color:#ffffff; font-size:24px; font-weight:900; }
            QLabel#guideHeroSubtitle { color:#e0f2fe; font-size:13px; }
            QPushButton#guidePdfButton { background:rgba(255,255,255,0.95); color:#1d4ed8; border:0; border-radius:10px; padding:10px 16px; font-weight:900; }
            QPushButton#guidePdfButton:hover { background:#ffffff; color:#1e40af; }
            QListWidget#guideNav { background:#ffffff; border:1px solid #dbe7f3; border-radius:14px; padding:8px; outline:0; }
            QListWidget#guideNav::item { color:#334155; border-radius:10px; padding:12px 10px; margin:2px; font-size:14px; font-weight:700; }
            QListWidget#guideNav::item:selected { background:#e0ecff; color:#1d4ed8; }
            QListWidget#guideNav::item:hover { background:#f1f5f9; }
            QStackedWidget#guideStack { background:#ffffff; border:1px solid #dbe7f3; border-radius:14px; }
            QLabel#guideParentTitle { font-size:12px; font-weight:900; color:#64748b; text-transform:uppercase; letter-spacing:0.8px; }
            QLabel#guidePageTitle { font-size:22px; font-weight:900; color:#102a56; }
            QLabel#guideImage { background:#f8fafc; border:1px dashed #cbd5e1; border-radius:14px; color:#64748b; font-size:13px; padding:16px; }
            QFrame#purposeCard, QFrame#actionsCard, QFrame#tipCard { background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; }
            QFrame#purposeCard { border-left:5px solid #1d4ed8; }
            QFrame#actionsCard { border-left:5px solid #0f766e; }
            QFrame#tipCard { background:#ffffff; border-left:5px solid #f97316; }
            QLabel#guideCardTitle { background:transparent; font-size:15px; font-weight:900; color:#1e3a8a; }
            QLabel#guideCardText { background:transparent; font-size:13px; line-height:1.35; color:#334155; }
            QPushButton#primaryButton { background:#1d4ed8; color:#ffffff; border:0; border-radius:10px; padding:10px 22px; font-weight:800; }
            QPushButton#primaryButton:hover { background:#1e40af; }
            QScrollArea { background:transparent; }
        """
