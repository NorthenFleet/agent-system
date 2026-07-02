from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
from fastapi.testclient import TestClient

app = FastAPI()
router = APIRouter()

class MsgReq(BaseModel):
    message: str

@router.get("/api/chat/{agent_id}/messages")
def get_msgs(agent_id: str):
    return {"agent_id": agent_id, "messages": []}

@router.post("/api/chat/{agent_id}/send")
async def send_msg(agent_id: str, req: MsgReq):
    return {"status": "ok", "message": req.message}

app.include_router(router)

client = TestClient(app)

# 测试
print("Test 1:", client.get("/api/chat/test/messages").status_code)
print("Test 2:", client.post("/api/chat/test/send", json={"message": "hi"}).status_code)
