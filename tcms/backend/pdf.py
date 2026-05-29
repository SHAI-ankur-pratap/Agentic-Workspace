import asyncio
import io
from functools import partial
from typing import Optional


def _render_pdf_sync(html: str) -> bytes:
    from weasyprint import HTML
    buf = io.BytesIO()
    HTML(string=html).write_pdf(buf)
    return buf.getvalue()


async def render_pdf(html: str) -> Optional[bytes]:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, partial(_render_pdf_sync, html))
    except Exception:
        return None
