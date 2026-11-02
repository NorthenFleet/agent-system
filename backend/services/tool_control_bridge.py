"""Per-attempt local controller transport. Credentials never enter model prompts."""
import asyncio
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path

PLUGIN_ID = 'mission-tool-control'
PLUGIN_PATH = Path(__file__).resolve().parents[2] / 'integrations/openclaw/mission-tool-control'
TOOLS = ['dr4_read', 'dr4_list', 'dr4_write', 'dr4_edit']


def enabled():
    return os.getenv('COMMAND_CENTER_TOOL_CONTROL_ENABLED', 'false').lower() == 'true'


class ToolControlBridge:
    def __init__(self, service, step):
        self.service, self.step = service, step
        self.token = secrets.token_hex(32)
        self.rejections = 0
        self.connections = set()
        self.closing = False

    async def __aenter__(self):
        # macOS Unix socket paths are short; keep state out of model-visible worktree.
        self.directory = tempfile.TemporaryDirectory(prefix='dr4-', dir='/tmp')
        self.socket_path = str(Path(self.directory.name) / 'control.sock')
        try:
            self.server = await asyncio.start_unix_server(self._handle, path=self.socket_path, limit=262145)
        except BaseException:
            self.directory.cleanup()
            raise
        os.chmod(self.socket_path, 0o600)
        return self

    async def __aexit__(self, *_):
        self.closing = True
        self.server.close()
        await self.server.wait_closed()
        pending = list(self.connections)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        self.directory.cleanup()

    async def _handle(self, reader, writer):
        task = asyncio.current_task()
        self.connections.add(task)
        try:
            try:
                data = await asyncio.wait_for(reader.readline(), 5)
                payload = json.loads(data)
                if self.closing or not isinstance(payload, dict) or not isinstance(payload.get('token'), str) or not hmac.compare_digest(payload['token'], self.token):
                    response = {'ok':False, 'error':'unauthorized_controller'}
                else:
                    response = self.service.execute_controlled_tool(self.step['id'], self.step['lease_token'],
                                payload.get('call_id'), payload.get('action'), payload.get('args'))
                if not response['ok']:
                    self.rejections += 1
            except Exception:
                self.rejections += 1
                response = {'ok':False, 'error':'controller_unavailable_or_authority_expired'}
            writer.write((json.dumps(response, ensure_ascii=False) + '\n').encode())
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, asyncio.CancelledError):
                pass
            self.connections.discard(task)

    def config(self, base):
        return {**base,
                'tools':{'profile':'full', 'allow':TOOLS, 'fs':{'workspaceOnly':True}},
                'plugins':{'enabled':True, 'allow':[PLUGIN_ID], 'load':{'paths':[str(PLUGIN_PATH)]},
                           'entries':{PLUGIN_ID:{'enabled':True, 'config':{'socketPath':self.socket_path,'token':self.token}}}}}

    def summary(self):
        summary = self.service.tool_control_summary(self.step['id'], self.step['attempt_count'])
        summary['transport_rejections'] = self.rejections
        summary['accepted'] = summary['accepted'] and self.rejections == 0
        return summary
