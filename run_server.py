from onwebchange.core import WebHandler
from onwebchange.webui import app

if __name__ == "__main__":
    wh = WebHandler(
        app,
        file_path=None,
        loop_interval=300,
        auto_open_browser=True,
        change_callback=lambda task: print(task.name),
        app_kwargs={'port': 9988})
    # python3 -m onwebchange -f wc.config -i 300
    wh.run()
