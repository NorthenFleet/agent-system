from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["bar"])


@router.get("/bar")
def get_bar_data():
    return {"bar": "placeholder"}
