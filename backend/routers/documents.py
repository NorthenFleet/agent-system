from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents")
def get_documents():
    return {"documents": []}
