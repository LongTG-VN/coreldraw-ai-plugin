"""Five controlled benchmark briefs with project-owned assets for the shootout."""

from __future__ import annotations

from pathlib import Path
from training.inference.planner_base import ContentLockSpec


BENCHMARK_BRIEFS: list[ContentLockSpec] = [
    ContentLockSpec(
        brief_id="brief_spa_01",
        category="SPA",
        business_name="SERENE SPA & WELLNESS",
        headline="THU GIAN & CHAM SOC DA CAO CAP",
        body="Lieu trinh thao moc thien nhiên giup phuc hoi sinh lau",
        cta="DAT LICH NGAY",
        price_offer="Voucher Giam 30%",
        logo_asset_id="spa_logo_01",
        hero_asset_id="spa_product_01",
        canvas_width_mm=210.0,
        canvas_height_mm=297.0,
    ),
    ContentLockSpec(
        brief_id="brief_cafe_01",
        category="CAFE",
        business_name="CHILL CAFE & TEA",
        headline="CA PHE PHIN & TRA SUA TUOI",
        body="Dam da huong vi truyen thong Sai Gon nguyen chat",
        cta="THUONG THUC NGAY",
        price_offer="Gia chi tu 25K",
        logo_asset_id="cafe_logo_01",
        hero_asset_id="cafe_product_01",
        canvas_width_mm=210.0,
        canvas_height_mm=297.0,
    ),
    ContentLockSpec(
        brief_id="brief_sale_01",
        category="SALE",
        business_name="URBAN FASHION STORE",
        headline="SUPER SUMMER SALE 2026",
        body="Chuong trinh khuyen mai lon nhat trong nam",
        cta="BUY NOW",
        price_offer="UP TO 50% OFF",
        logo_asset_id="sale_logo_01",
        hero_asset_id="sale_product_01",
        canvas_width_mm=210.0,
        canvas_height_mm=297.0,
    ),
    ContentLockSpec(
        brief_id="brief_menu_01",
        category="MENU",
        business_name="BEP VIET RESTAURANT",
        headline="DIEM TAM & MON AN SANG",
        body="Thuc don phong phu dinh duong moi ngay cho gia dinh",
        cta="GOI MON NGAY",
        price_offer="Dong gia 35K",
        logo_asset_id="menu_logo_01",
        hero_asset_id="menu_product_01",
        canvas_width_mm=210.0,
        canvas_height_mm=297.0,
    ),
    ContentLockSpec(
        brief_id="brief_signage_01",
        category="SIGNAGE",
        business_name="VIP DENTAL CLINIC",
        headline="NHA KHOA THAM MY QUOC TE",
        body="Cham soc nu cuoi Viet - Cong nghe Chau Au",
        cta="HOTLINE: 0988.789.999",
        price_offer="Kham & Tu van Mien phi",
        logo_asset_id="signage_logo_01",
        hero_asset_id="",
        canvas_width_mm=300.0,
        canvas_height_mm=100.0,
    ),
]


def get_brief_by_id(brief_id: str) -> ContentLockSpec:
    for brief in BENCHMARK_BRIEFS:
        if brief.brief_id == brief_id:
            return brief
    raise ValueError(f"Unknown brief_id: {brief_id}")
