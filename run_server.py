from onwebchange.core import WebHandler
from onwebchange.webui import app

if __name__ == "__main__":
    wh = WebHandler(
        app,
        file_path=None,
        loop_interval=300,
        auto_open_browser=True,
        app_kwargs={'port': 9988},
        username='',
        password='')
    # python3 -m onwebchange -f wc.config -i 300 --host=127.0.0.1 -p 8080 --username=admin --password=admin
    wh.run()
