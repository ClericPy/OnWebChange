from onwebchange.core import WebHandler
from onwebchange.webui import app

if __name__ == "__main__":
    wh = WebHandler(app)
    wh.loop.run_until_complete(wh.run_server())
