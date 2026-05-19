# -*- coding: utf-8 -*-
from pathlib import Path

from src.domain.constants import MAIN_COLUMN_HEADERS

APP_TITLE = "KONFİGÜRASYON YÖNETİMİ SÖZLEŞME TAKİP SİSTEMİ"
DEFAULT_FILE = "sozlesme_takip_data.xlsx"
APP_ICON_PATH = Path(__file__).resolve().parents[1] / "ui" / "assets" / "sts_logo.svg"
APP_ICON_ICO_PATH = Path(__file__).resolve().parents[1] / "ui" / "assets" / "sts_icon.ico"
APP_ID = "Baykar.STS.ContractTracking"
COMP_SHEET = "Sistem Bileşenleri"
USERS_SHEET = "Kullanıcılar"
PLATFORM_LOGO_SHEET = "Platform Logolari"
TAG_SHEET = "Etiketler"
TAG_KIND_DEF = "ETIKET"
TAG_KIND_ASSIGN = "ATAMA"
LOG_FOLDER_NAME = "sozlesme_takip_sistemi_log"

NAVY = "002060"
LIGHT = "E8EEF5"
CARD = "FFFFFF"
HEAD = "EEF2F6"
BLUE = "1F5BE3"
GREEN = "C6EFCE"
GRID = "D8E2ED"
TEXT_MUTED = "64748B"

BASE_HEADERS = MAIN_COLUMN_HEADERS
MAIN_TOTAL_LABEL = "Ana Sözleşme Toplamı"
SYSTEM_TOTAL_SUFFIX = "Toplamı"
TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
]
TR_WEEKDAYS = ["PAZ", "PZT", "SAL", "ÇAR", "PER", "CUM", "CMT"]
LOG_HEADERS = ["Tarih", "Kullanıcı", "Platform", "Sözleşme", "Teslimat", "Tür", "Bileşen", "Alan", "Eski", "Yeni", "Neden"]
TAG_HEADERS = ["KayitTipi", "EtiketAdi", "Renk", "AciklamaNot", "Aktif", "Platform", "SozlesmeNo", "SozlesmeTipi", "AtamaTarihi", "Kullanici"]

EXTRA_SYSTEM_SHEET_NAMES = {
    "config",
    "degisiklik kayitlari",
    "etiketler",
    "vericekme",
    "sistem bilesenleri",
    "sistemtipleri",
    "sistem tipleri",
    "kullanicilar",
    "platform logolari",
}
