"""
新闻资讯抓取服务
任务 007: 新闻资讯热力图地球
"""
from datetime import datetime
from typing import List, Dict, Optional

class NewsScraper:
    """新闻抓取器"""
    
    def __init__(self):
        self.cache: List[Dict] = []
        self.last_update: Optional[datetime] = None
    
    def fetch_news(self, category: Optional[str] = None) -> List[Dict]:
        """获取新闻（模拟数据）"""
        mock_news = [
            {
                'id': '1',
                'title': 'AI 技术新突破：多模态模型能力大幅提升',
                'summary': '最新研究显示，新一代多模态 AI 模型在图像理解和语言生成方面取得重大进展',
                'category': '科技',
                'source': '科技日报',
                'location': '北京',
                'lat': 39.9042,
                'lng': 116.4074,
                'timestamp': datetime.now().isoformat()
            },
            {
                'id': '2',
                'title': '全球股市震荡，科技股领涨',
                'summary': '受美联储政策影响，全球主要股市出现波动',
                'category': '财经',
                'source': '财经网',
                'location': '纽约',
                'lat': 40.7128,
                'lng': -74.0060,
                'timestamp': datetime.now().isoformat()
            },
            {
                'id': '3',
                'title': '国际气候峰会达成新协议',
                'summary': '各国代表就减少碳排放达成新的共识',
                'category': '政治',
                'source': '国际新闻',
                'location': '巴黎',
                'lat': 48.8566,
                'lng': 2.3522,
                'timestamp': datetime.now().isoformat()
            }
        ]
        
        if category:
            mock_news = [n for n in mock_news if n['category'] == category]
        
        self.cache = mock_news
        self.last_update = datetime.now()
        
        return mock_news
    
    def get_heatmap_data(self) -> List[Dict]:
        """获取热力图数据"""
        return [
            {'lat': 39.9042, 'lng': 116.4074, 'intensity': 0.8},
            {'lat': 40.7128, 'lng': -74.0060, 'intensity': 0.6},
            {'lat': 48.8566, 'lng': 2.3522, 'intensity': 0.7},
            {'lat': 51.5074, 'lng': -0.1278, 'intensity': 0.5},
            {'lat': 35.6762, 'lng': 139.6503, 'intensity': 0.9}
        ]
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_news': len(self.cache),
            'hot_regions': len(set(n['location'] for n in self.cache)),
            'last_update': self.last_update.isoformat() if self.last_update else None
        }

news_scraper = NewsScraper()
