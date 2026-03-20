from fastapi import APIRouter, Depends, HTTPException, Header

from config import get_settings
from scheduler import is_paused, set_paused

router = APIRouter(prefix="/api", tags=["auth"])


def verify_api_key(x_api_key: str = Header()):
    settings = get_settings()
    if x_api_key != settings.api_secret_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/health")
def health():
    return {"status": "ok", "paused": is_paused()}


@router.post("/pause", dependencies=[Depends(verify_api_key)])
def pause_trading():
    set_paused(True)
    return {"message": "자동매매 일시정지", "paused": True}


@router.post("/resume", dependencies=[Depends(verify_api_key)])
def resume_trading():
    set_paused(False)
    return {"message": "자동매매 재개", "paused": False}
