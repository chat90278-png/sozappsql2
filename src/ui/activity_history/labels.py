from __future__ import annotations

from src.services.activity_history_infra import canonical_activity_action


ACTION_LABELS_TR = {
    "contract_created": "Sözleşme oluşturuldu",
    "contract_updated": "Sözleşme güncellendi",
    "contract_deleted": "Sözleşme silindi",
    "contract_status_changed": "Sözleşme durumu değiştirildi",
    "contract_tags_updated": "Sözleşme etiketleri güncellendi",
    "system_created": "Sistem oluşturuldu",
    "system_updated": "Sistem güncellendi",
    "system_deleted": "Sistem silindi",
    "system_component_updated": "Sistem bileşeni güncellendi",
    "delivery_created": "Teslimat oluşturuldu",
    "delivery_updated": "Teslimat güncellendi",
    "delivery_deleted": "Teslimat silindi",
    "delivery_status_changed": "Teslimat durumu değiştirildi",
    "document_added": "Belge eklendi",
    "document_updated": "Belge güncellendi",
    "document_deleted": "Belge silindi",
    "document_moved": "Belge taşındı",
    "document_renamed": "Belge yeniden adlandırıldı",
    "documents_locked": "Belgeler kilitlendi",
    "documents_unlocked": "Belge kilidi açıldı",
    "share_merge_applied": "Paylaşım değişiklikleri birleştirildi",
    "platform_created": "Platform oluşturuldu",
    "platform_updated": "Platform güncellendi",
    "platform_deleted": "Platform silindi",
    "platform_order_changed": "Platform sırası değiştirildi",
    "platform_exclusions_updated": "Platform hariç tutma ayarları güncellendi",
    "platform_logo_updated": "Platform logosu güncellendi",
    "users_updated": "Kullanıcı listesi güncellendi",
    "user_created": "Kullanıcı oluşturuldu",
    "user_updated": "Kullanıcı güncellendi",
    "user_deleted": "Kullanıcı silindi",
    "components_updated": "Bileşen listesi güncellendi",
    "component_created": "Bileşen oluşturuldu",
    "component_updated": "Bileşen güncellendi",
    "component_deleted": "Bileşen silindi",
    "tag_created": "Etiket oluşturuldu",
    "tag_updated": "Etiket güncellendi",
    "tag_deleted": "Etiket silindi",
    "tag_snapshot_updated": "Etiket görünümü güncellendi",
    "sql_query_executed": "Veri değiştiren SQL sorgusu çalıştırıldı",
    "database_backup_created": "Veritabanı yedeği oluşturuldu",
    "database_optimized": "Veritabanı optimize edildi",
    "database_vacuumed": "Veritabanı bakımı tamamlandı",
    "excel_exported": "Excel dışa aktarımı tamamlandı",
    "excel_export_failed": "Excel dışa aktarımı başarısız oldu",
}

_TOKEN_LABELS_TR = {
    "contract": "sözleşme",
    "contracts": "sözleşmeler",
    "system": "sistem",
    "delivery": "teslimat",
    "document": "belge",
    "documents": "belgeler",
    "platform": "platform",
    "user": "kullanıcı",
    "users": "kullanıcılar",
    "component": "bileşen",
    "components": "bileşenler",
    "tag": "etiket",
    "tags": "etiketler",
    "database": "veritabanı",
    "excel": "Excel",
    "status": "durumu",
    "order": "sırası",
    "created": "oluşturuldu",
    "updated": "güncellendi",
    "deleted": "silindi",
    "changed": "değiştirildi",
    "added": "eklendi",
    "moved": "taşındı",
    "renamed": "yeniden adlandırıldı",
    "locked": "kilitlendi",
    "unlocked": "kilidi açıldı",
    "exported": "dışa aktarıldı",
    "failed": "başarısız oldu",
}


def visible_action_label(action: str, provided_label: str = "") -> str:
    """Return a stable Turkish UI label without changing stored action codes."""

    canonical = canonical_activity_action(action)
    if canonical in ACTION_LABELS_TR:
        return ACTION_LABELS_TR[canonical]

    parts = [part for part in canonical.replace("-", "_").split("_") if part]
    if parts:
        translated = [_TOKEN_LABELS_TR.get(part, part) for part in parts]
        text = " ".join(translated).strip()
        if text:
            return text[:1].upper() + text[1:]

    supplied = str(provided_label or "").strip()
    return supplied or "Bilinmeyen işlem"


__all__ = ["ACTION_LABELS_TR", "visible_action_label"]
