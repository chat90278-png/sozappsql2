from __future__ import annotations

from dataclasses import dataclass

from src.domain.share_merge_resolution import InvalidMergeDecisionError, UnresolvedMergeConflictError
from src.services.share_merge_apply_service import (
    MergeOperationApplyError,
    MergeOperationTargetNotFoundError,
    MergePackageChangedError,
    MergeSourceChangedError,
    MergeTransactionError,
    RemoteDocumentHashMismatchError,
    RemoteDocumentNotFoundError,
    ShareMergeApplyValidationError,
    SharePackageAlreadyAppliedError,
)
from src.services.share_merge_service import (
    PackageRegistryMismatchError,
    ShareMergePreparationError,
    SharePackageStatusError,
    ShareSourceMismatchError,
    UnknownSharePackageError,
    UnsupportedShareMergePackageError,
)


@dataclass(frozen=True)
class ShareMergeErrorPresentation:
    title: str
    message: str
    detail: str = ""
    severity: str = "warning"


def present_share_merge_error(exc: Exception) -> ShareMergeErrorPresentation:
    detail = str(exc or "")
    mapping: tuple[tuple[type[BaseException], str, str], ...] = (
        (ShareSourceMismatchError, "Paylaşım dosyası birleştirilemedi", "Seçilen paylaşım dosyası bu STS dosyasına ait değil."),
        (UnknownSharePackageError, "Paylaşım dosyası birleştirilemedi", "Bu paylaşım paketi ana STS kayıtlarında bulunamadı."),
        (PackageRegistryMismatchError, "Paylaşım dosyası birleştirilemedi", "Paylaşım paketi kayıt bilgileri ana STS ile uyuşmuyor."),
        (SharePackageStatusError, "Paylaşım dosyası birleştirilemedi", "Bu paylaşım paketinin durumu birleştirmeye kapalı."),
        (UnsupportedShareMergePackageError, "Paylaşım dosyası birleştirilemedi", "Seçilen dosya geçerli ve desteklenen bir V2 paylaşım paketi değil."),
        (ShareMergePreparationError, "Paylaşım dosyası birleştirilemedi", "Paylaşım dosyası merge için hazırlanamadı."),
        (SharePackageAlreadyAppliedError, "Paylaşım dosyası birleştirilemedi", "Bu paylaşım dosyasındaki değişiklikler daha önce birleştirilmiş."),
        (MergeSourceChangedError, "Paylaşım dosyası birleştirilemedi", "Ana STS, plan hazırlandıktan sonra değişmiş. Lütfen birleştirmeyi yeniden başlatın."),
        (MergePackageChangedError, "Paylaşım dosyası birleştirilemedi", "Paylaşım dosyası, plan hazırlandıktan sonra değişmiş."),
        (RemoteDocumentNotFoundError, "Paylaşım dosyası birleştirilemedi", "Paylaşım dosyasındaki belge içeriği bulunamadı."),
        (RemoteDocumentHashMismatchError, "Paylaşım dosyası birleştirilemedi", "Paylaşım dosyasındaki belge içeriği doğrulanamadı."),
        (MergeOperationTargetNotFoundError, "Paylaşım dosyası birleştirilemedi", "Birleştirme hedeflerinden biri bulunamadı."),
        (MergeOperationApplyError, "Paylaşım dosyası birleştirilemedi", "Birleştirme işlemlerinden biri uygulanamadı."),
        (MergeTransactionError, "Paylaşım dosyası birleştirilemedi", "Birleştirme işlemi başlatılamadı."),
        (ShareMergeApplyValidationError, "Paylaşım dosyası birleştirilemedi", "Birleştirme ön kontrolü başarısız oldu."),
        (UnresolvedMergeConflictError, "Paylaşım dosyası birleştirilemedi", "Tüm çakışmalar için açık karar verilmeden devam edilemez."),
        (InvalidMergeDecisionError, "Paylaşım dosyası birleştirilemedi", "Seçilen birleştirme kararı geçerli değil."),
    )
    for cls, title, message in mapping:
        if isinstance(exc, cls):
            return ShareMergeErrorPresentation(title=title, message=message, detail=detail, severity="warning")
    return ShareMergeErrorPresentation(
        title="Paylaşım dosyası birleştirilemedi",
        message="Beklenmeyen bir hata oluştu. Lütfen işlemi yeniden deneyin veya günlükleri kontrol edin.",
        detail=detail,
        severity="error",
    )
