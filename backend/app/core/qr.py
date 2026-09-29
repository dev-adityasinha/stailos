"""QR code generation — free/open-source `qrcode` package. Used for event
check-in badges (encodes a registration's opaque checkin_token/URL)."""
import io

import qrcode


def build_qr_png(data: str) -> bytes:
    img = qrcode.make(data, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
