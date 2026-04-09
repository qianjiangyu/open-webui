import base64
import random
import time
import uuid

from fastapi import HTTPException, status

# 最小可用版本：进程内缓存
# 单机部署没问题；多副本/K8s/负载均衡时建议改成 Redis
_CAPTCHA_STORE: dict[str, dict] = {}
_CAPTCHA_TTL_SECONDS = 120
_CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _cleanup_expired_captcha() -> None:
    now = time.time()
    expired_keys = [
        captcha_id
        for captcha_id, item in _CAPTCHA_STORE.items()
        if item["expires_at"] <= now
    ]
    for captcha_id in expired_keys:
        _CAPTCHA_STORE.pop(captcha_id, None)


def _generate_captcha_text(length: int = 4) -> str:
    return "".join(random.choice(_CAPTCHA_CHARS) for _ in range(length))


def _generate_svg_data_uri(text: str) -> str:
    letters = []
    x = 16
    for ch in text:
        dy = random.randint(-2, 6)
        rotate = random.randint(-18, 18)
        letters.append(
            f"""
            <text
                x="{x}"
                y="{28 + dy}"
                font-size="24"
                font-family="Arial, Helvetica, sans-serif"
                fill="#111827"
                transform="rotate({rotate} {x} 28)"
            >{ch}</text>
            """
        )
        x += 22

    noise = []
    for _ in range(5):
        x1 = random.randint(0, 120)
        y1 = random.randint(0, 40)
        x2 = random.randint(0, 120)
        y2 = random.randint(0, 40)
        noise.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9CA3AF" stroke-width="1" />'
        )

    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="120" height="40" viewBox="0 0 120 40">
        <rect width="120" height="40" rx="8" fill="#F9FAFB" />
        {''.join(noise)}
        {''.join(letters)}
    </svg>
    """

    encoded = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded}"


def create_captcha() -> dict:
    _cleanup_expired_captcha()

    captcha_id = str(uuid.uuid4())
    captcha_code = _generate_captcha_text()

    _CAPTCHA_STORE[captcha_id] = {
        "code": captcha_code.lower(),
        "expires_at": time.time() + _CAPTCHA_TTL_SECONDS,
    }

    return {
        "captcha_id": captcha_id,
        "image": _generate_svg_data_uri(captcha_code),
        "expires_in": _CAPTCHA_TTL_SECONDS,
    }


def verify_captcha(captcha_id: str, captcha_code: str) -> None:
    _cleanup_expired_captcha()

    captcha = _CAPTCHA_STORE.get(captcha_id)
    if captcha is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Captcha expired, please refresh and try again.",
        )

    normalized_code = (captcha_code or "").strip().lower()
    if normalized_code != captcha["code"]:
        _CAPTCHA_STORE.pop(captcha_id, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid captcha.",
        )

    _CAPTCHA_STORE.pop(captcha_id, None)