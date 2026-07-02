#!/usr/bin/env python3
"""
智能体消息服务
通过 OpenClaw 发送和接收消息
"""

import json
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

# 消息存储目录
MESSAGES_DIR = os.path.expanduser("~/.openclaw/workspace/messages")
os.makedirs(MESSAGES_DIR, exist_ok=True)

OPENCLAW_BIN = os.getenv(
    "OPENCLAW_BIN",
    "/opt/homebrew/opt/node/bin/openclaw",
)
OPENCLAW_PATH = os.getenv(
    "OPENCLAW_PATH",
    "/opt/homebrew/opt/node/bin:/opt/homebrew/Cellar/node/25.6.1_1/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
)


class AgentMessenger:
    """智能体消息管理器"""
    
    def __init__(self):
        self.messages_dir = MESSAGES_DIR
    
    def _get_conversation_file(self, agent_id: str) -> str:
        return os.path.join(self.messages_dir, f"{agent_id}_conversation.json")
    
    def load_conversation(self, agent_id: str) -> List[Dict]:
        filepath = self._get_conversation_file(agent_id)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_conversation(self, agent_id: str, messages: List[Dict]):
        filepath = self._get_conversation_file(agent_id)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    
    def add_message(self, agent_id: str, role: str, content: str, attachments: Optional[List[Dict]] = None) -> Dict:
        messages = self.load_conversation(agent_id)
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        if attachments:
            message["attachments"] = attachments
        messages.append(message)
        self.save_conversation(agent_id, messages)
        return message
    
    async def send_to_agent(self, agent_id: str, message: str, attachments: Optional[List[Dict]] = None) -> Dict:
        """发送消息到指定智能体"""
        safe_attachments = self._normalize_attachments(attachments or [])
        openclaw_message = self._compose_openclaw_message(message, safe_attachments)
        response_text = await self._call_openclaw(agent_id, openclaw_message)

        self.add_message(agent_id, "user", message, safe_attachments)
        self.add_message(agent_id, "agent", response_text)
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "user_message": message,
            "agent_response": response_text,
            "attachments": safe_attachments,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_agent_name(self, agent_id: str) -> str:
        """获取智能体显示名称"""
        names = {
            "optimus": "擎天柱",
            "bumblebee": "大黄蜂",
            "leonardo": "李奥纳多",
            "raphael": "拉斐尔",
            "donatello": "多纳泰罗",
            "michelangelo": "米开朗基罗",
            "ironhide": "铁皮",
            "perceptor": "感知器",
            "wheeljack": "千斤顶",
            "shockwave": "震荡波",
        }
        return names.get(agent_id, agent_id)

    def _normalize_attachments(self, attachments: List[Dict]) -> List[Dict]:
        normalized = []
        for item in attachments[:6]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "未命名附件")[:160]
            content_type = str(item.get("type") or "application/octet-stream")[:120]
            try:
                size = int(item.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            data_url = item.get("data_url")
            if not isinstance(data_url, str):
                data_url = None
            if data_url and len(data_url) > 1_500_000:
                data_url = None

            normalized.append({
                "id": str(item.get("id") or name),
                "name": name,
                "type": content_type,
                "size": size,
                "data_url": data_url,
            })
        return normalized

    def _compose_openclaw_message(self, message: str, attachments: List[Dict]) -> str:
        if not attachments:
            return message

        lines = [message.strip() or "请结合附件内容进行分析。", "", "【用户随消息附加的多模态材料】"]
        for index, attachment in enumerate(attachments, start=1):
            lines.append(
                f"{index}. {attachment['name']} | {attachment['type']} | {attachment['size']} bytes"
            )
            data_url = attachment.get("data_url")
            if data_url:
                if attachment["type"].startswith("image/"):
                    lines.append(f"   图片 data URL: {data_url[:120000]}")
                else:
                    lines.append("   文件已随看板消息保存；如需原文，请根据文件名向用户确认或要求粘贴内容。")
            else:
                lines.append("   附件内容未内联，当前仅可参考文件名、类型和大小。")
        return "\n".join(lines)
    
    async def _call_openclaw(self, agent_id: str, message: str) -> Optional[str]:
        """调用 OpenClaw CLI 发送消息"""
        cmd = [
            OPENCLAW_BIN,
            "agent",
            "--agent",
            agent_id,
            "--message",
            message,
            "--json",
        ]

        env = os.environ.copy()
        env["PATH"] = OPENCLAW_PATH

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            raise RuntimeError(stderr_text.strip() or stdout_text.strip() or "OpenClaw agent 调用失败")

        try:
            result = json.loads(stdout_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenClaw 返回了非 JSON 输出：{stdout_text[:500]}") from exc

        response_text = self._extract_openclaw_text(result)
        if not response_text:
            raise RuntimeError(f"OpenClaw 未返回可显示文本：{json.dumps(result, ensure_ascii=False)[:500]}")
        return response_text

    def _extract_openclaw_text(self, result: Dict) -> str:
        payloads = result.get("result", {}).get("payloads", [])
        if isinstance(payloads, list):
            texts = [
                str(item.get("text", "")).strip()
                for item in payloads
                if isinstance(item, dict) and item.get("text")
            ]
            if texts:
                return "\n\n".join(texts)

        for key in ("finalAssistantVisibleText", "finalAssistantRawText"):
            text = result.get("result", {}).get(key)
            if isinstance(text, str) and text.strip():
                return text.replace("[[reply_to_current]]", "").strip()

        for key in ("response", "message", "text"):
            text = result.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
        return ""
    
    def get_conversations_list(self) -> List[Dict]:
        conversations = []
        if os.path.exists(self.messages_dir):
            for filename in os.listdir(self.messages_dir):
                if filename.endswith("_conversation.json"):
                    agent_id = filename.replace("_conversation.json", "")
                    messages = self.load_conversation(agent_id)
                    conversations.append({
                        "agent_id": agent_id,
                        "message_count": len(messages),
                        "last_message": messages[-1] if messages else None,
                        "last_timestamp": messages[-1]["timestamp"] if messages else None
                    })
        return sorted(conversations, key=lambda x: x.get("last_timestamp") or "", reverse=True)
    
    def clear_conversation(self, agent_id: str) -> bool:
        filepath = self._get_conversation_file(agent_id)
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False


# 全局实例
agent_messenger = AgentMessenger()


if __name__ == "__main__":
    async def test():
        messenger = AgentMessenger()
        result = await messenger.send_to_agent("optimus", "你好，请汇报当前状态")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())
