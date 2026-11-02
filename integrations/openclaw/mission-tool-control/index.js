import net from 'node:net';

export function request(config, payload) {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({path: config.socketPath});
    socket.setEncoding('utf8');
    let buffer = '';
    const finish = (error, value) => { socket.destroy(); error ? reject(error) : resolve(value); };
    socket.setTimeout(10000, () => finish(new Error('Tool controller timeout')));
    socket.on('error', error => finish(error));
    socket.on('connect', () => socket.write(JSON.stringify({...payload, token: config.token}) + '\n'));
    socket.on('data', chunk => {
      buffer += chunk;
      if (Buffer.byteLength(buffer) > 1500000) return finish(new Error('Tool response exceeds budget'));
      const end = buffer.indexOf('\n');
      if (end >= 0) {
        try { finish(null, JSON.parse(buffer.slice(0, end))); } catch (error) { finish(error); }
      }
    });
    socket.on('end', () => { if (!buffer.includes('\n')) finish(new Error('Incomplete tool receipt')); });
  });
}

export default {
  id: 'mission-tool-control',
  name: 'Mission Tool Control',
  register(api) {
    const config = api.pluginConfig;
    if (!config?.socketPath || !config?.token) throw new Error('Missing tool controller');
    for (const action of ['read', 'list', 'write', 'edit']) {
      const properties = {path: {type: 'string', description: 'Relative path inside the approved candidate worktree'}};
      const required = ['path'];
      if (action === 'write') { properties.content = {type:'string'}; required.push('content'); }
      if (action === 'edit') {
        properties.old_text = {type:'string'}; properties.new_text = {type:'string'};
        required.push('old_text','new_text');
      }
      api.registerTool({name: `dr4_${action}`, label: `Controlled ${action}`,
        description: `Mission-controlled ${action}. Authority, path and call budget checked before execution; durable receipt afterwards.`,
        parameters: {type:'object', properties, required, additionalProperties:false},
        async execute(callId, params) {
          const response = await request(config, {call_id:callId, action, args:params});
          if (!response.ok) throw new Error(`Tool rejected: ${response.error || 'controller_rejected'}`);
          return {content:[{type:'text', text:response.output}], details:{receipt:response.receipt}};
        }
      });
    }
  }
};
