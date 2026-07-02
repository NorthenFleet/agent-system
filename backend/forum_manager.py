"""Stub for forum_manager."""
class ForumManager:
    def __getattr__(self, name):
        return lambda *a, **k: {"error": "not implemented"}
forum_manager = ForumManager()
