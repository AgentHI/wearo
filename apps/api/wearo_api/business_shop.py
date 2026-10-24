from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import UUID

import qrcode
from PIL import Image, ImageChops, ImageDraw, ImageFont
from sqlalchemy import Engine, text

from .tenant_scope import TenantScopeError, require_tenant_scope


class BusinessShopError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


ASSET_DIR = Path(__file__).with_name("assets")


def _font(name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default(size=size)


def _content_crop(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    difference = ImageChops.difference(rgb, background).convert("L")
    bounds = difference.point(lambda pixel: 255 if pixel > 20 else 0).getbbox()
    return image.crop(bounds) if bounds else image


def _paste_contained(
    canvas: Image.Image, source: Image.Image, box: tuple[int, int, int, int]
) -> None:
    width, height = box[2] - box[0], box[3] - box[1]
    prepared = source.convert("RGBA")
    prepared.thumbnail((width, height), Image.Resampling.LANCZOS)
    x = box[0] + (width - prepared.width) // 2
    y = box[1] + (height - prepared.height) // 2
    canvas.paste(prepared, (x, y), prepared)


def qr_poster(shop_url: str, business_name: str, logo: bytes | None = None) -> bytes:
    with Image.open(ASSET_DIR / "qr-poster-luxury-background.png") as background:
        poster = background.convert("RGB").resize((1122, 1402), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(poster)
    sans = _font("DejaVuSans.ttf", 32)
    sans_bold = _font("DejaVuSans-Bold.ttf", 36)
    serif = _font("DejaVuSerif-Bold.ttf", 80)
    serif_gold = _font("DejaVuSerif-Bold.ttf", 86)

    # Business identity and Wearo endorsement.
    if logo:
        try:
            with Image.open(BytesIO(logo)) as source:
                _paste_contained(poster, _content_crop(source), (270, 40, 365, 125))
        except (OSError, ValueError):
            logo = None
    if not logo:
        initials = "".join(part[0] for part in business_name.split()[:2]).upper() or "B"
        draw.rounded_rectangle((280, 48, 350, 118), radius=14, fill="#461044")
        draw.text((315, 83), initials, fill="white", font=sans_bold, anchor="mm")
    display_name = business_name[:28]
    draw.text((380, 82), display_name, fill="#22122c", font=sans_bold, anchor="lm")
    draw.line((720, 40, 720, 125), fill="#c99851", width=2)
    with Image.open(ASSET_DIR / "wearo-brand.png") as brand:
        _paste_contained(poster, _content_crop(brand), (755, 30, 1070, 135))

    # Campaign message, kept as deterministic text for perfect spelling.
    draw.text((750, 220), "Try Before", fill="#3d073d", font=serif, anchor="mm")
    draw.text((750, 305), "You Buy", fill="#a65b09", font=serif_gold, anchor="mm")
    draw.line((570, 358, 930, 358), fill="#c98b35", width=2)
    draw.text(
        (750, 402),
        "Scan to experience virtual try-on",
        fill="#32123a",
        font=sans,
        anchor="mm",
    )
    draw.text((750, 442), "with confidence.", fill="#32123a", font=sans, anchor="mm")

    # High-contrast QR panel with a generous quiet zone.
    qr_code = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=1,
        border=4,
    )
    qr_code.add_data(shop_url)
    qr_code.make(fit=True)
    qr_code.box_size = max(1, 410 // (qr_code.modules_count + 8))
    qr = qr_code.make_image(fill_color="black", back_color="white").convert("RGB")
    draw.rounded_rectangle(
        (522, 490, 978, 946), radius=30, fill="white", outline="#e7b85c", width=5
    )
    poster.paste(qr, (750 - qr.width // 2, 718 - qr.height // 2))

    # Call to action and trust cues.
    draw.rounded_rectangle(
        (385, 1000, 985, 1100), radius=50, fill="#4a1248", outline="#e8bb69", width=5
    )
    draw.text((675, 1050), "SCAN NOW  ›", fill="#fff5dd", font=serif, anchor="mm")
    draw.text((675, 1140), "Buy confidently!", fill="white", font=sans_bold, anchor="mm")
    draw.line((390, 1140, 520, 1140), fill="#d9a958", width=2)
    draw.line((830, 1140, 960, 1140), fill="#d9a958", width=2)
    cues = ((430, "VIRTUAL TRY-ON"), (675, "PRIVATE BY DESIGN"), (920, "POWERED BY WEARO"))
    cue_font = _font("DejaVuSans-Bold.ttf", 20)
    for x, label in cues:
        draw.ellipse((x - 28, 1190, x + 28, 1246), outline="#e5b65e", width=3)
        draw.polygon(
            ((x, 1202), (x + 15, 1218), (x, 1234), (x - 15, 1218)),
            outline="#f4d28d",
            width=3,
        )
        draw.text((x, 1280), label, fill="white", font=cue_font, anchor="mm")

    output = BytesIO()
    poster.save(output, format="PNG", optimize=True, dpi=(300, 300))
    return output.getvalue()


class PostgresBusinessShop:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def details(self, principal_id: UUID, tenant_id: UUID, origin: str) -> dict[str, object]:
        with self.engine.connect() as connection:
            try:
                account_id = require_tenant_scope(
                    connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
                ).account_id
            except TenantScopeError:
                raise BusinessShopError("SHOP_LINK_UNAVAILABLE", "Resource unavailable.") from None
            row = (
                connection.execute(
                    text(
                        """SELECT l.public_token, l.public_code, l.caption, l.enabled,
                              p.display_name, p.logo_asset_id, t.slug
                    FROM business_shop_links l JOIN business_profiles p
                      ON p.tenant_id=l.tenant_id AND p.account_id=l.account_id
                    JOIN business_tenants t
                      ON t.tenant_id=l.tenant_id AND t.account_id=l.account_id
                    WHERE l.tenant_id=:tenant AND l.account_id=:account"""
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise BusinessShopError("SHOP_LINK_UNAVAILABLE", "Resource unavailable.")
        shop_url = f"{origin.rstrip('/')}/shop/{row['slug']}?key={row['public_code']}"
        return {
            **dict(row),
            "account_id": account_id,
            "business_id": tenant_id,
            "shop_url": shop_url,
            "agent_url": f"{origin.rstrip('/')}/agent/{row['slug']}?key={row['public_code']}",
        }

    def public_details(self, business_reference: str, public_key: str) -> dict[str, object]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT l.tenant_id, l.account_id, p.display_name,
                                  p.operating_profile, l.caption, p.logo_asset_id
                    FROM business_shop_links l JOIN business_profiles p
                      ON p.tenant_id=l.tenant_id AND p.account_id=l.account_id
                    JOIN business_tenants t
                      ON t.tenant_id=l.tenant_id AND t.account_id=l.account_id
                    WHERE (t.slug=:reference OR CAST(l.tenant_id AS text)=:reference)
                      AND (l.public_code=:key OR CAST(l.public_token AS text)=:key)
                      AND l.enabled"""
                    ),
                    {"reference": business_reference, "key": public_key},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise BusinessShopError("SHOP_LINK_UNAVAILABLE", "Shop is unavailable.")
            return {
                "business_id": row["tenant_id"],
                **dict(row),
                "logo_url": (
                    f"/api/v1/public/shops/{business_reference}/logo?key={public_key}"
                    if row["logo_asset_id"] is not None
                    else None
                ),
            }

    def set_logo(self, principal_id: UUID, tenant_id: UUID, asset_id: UUID) -> dict[str, object]:
        with self.engine.begin() as connection:
            try:
                account_id = require_tenant_scope(
                    connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
                ).account_id
            except TenantScopeError:
                raise BusinessShopError("SHOP_LINK_UNAVAILABLE", "Resource unavailable.") from None
            updated = connection.execute(
                text(
                    """UPDATE business_profiles SET logo_asset_id=:asset, updated_at=now()
                    WHERE tenant_id=:tenant AND account_id=:account
                    RETURNING logo_asset_id"""
                ),
                {"asset": asset_id, "tenant": tenant_id, "account": account_id},
            ).scalar_one_or_none()
            if updated is None:
                raise BusinessShopError("SHOP_LINK_UNAVAILABLE", "Resource unavailable.")
        return {"logo_asset_id": updated}
