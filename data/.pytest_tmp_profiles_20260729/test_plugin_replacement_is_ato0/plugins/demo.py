
from core.plugin_manager import BasePlugin
class DemoPlugin(BasePlugin):
    name = "demo"
    description = "demo"
    triggers = ["comando muito especifico"]
    def handle(self, text, context):
        return None

VERSION = 'new'
