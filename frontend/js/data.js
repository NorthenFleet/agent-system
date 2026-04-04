// 数据定义模块
export const initialState = {
  agents: [],
  selectedAgent: null,
  loading: false,
  error: null
};

export const statusMap = {
  online: { text: '在线', type: 'success' },
  busy: { text: '忙碌', type: 'warning' },
  idle: { text: '空闲', type: 'info' },
  pending: { text: '待机', type: 'info' }
};

export const teamMap = {
  autobots: '汽车人',
  ninja_turtles: '忍者神龟',
  decepticons: '霸天虎'
};
