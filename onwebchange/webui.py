import traceback

from bottle import Bottle, request

from .core import WatchdogCage, WatchdogTask

# app.wc = xxx
app = Bottle()


@app.get('/get_task')
def get_task():
    task_name = request.GET.get('name')
    return app.wc.get_task(task_name)


@app.post('/update_task')
def update_task():
    # receive a standard task json
    task_json = request.json
    try:
        task = WatchdogTask.load_task(task_json)
        ok = app.wc.update_task(task)
    except:
        app.wc.logger.error(traceback.format_exc())
        ok = False
    return {'ok': ok}


@app.get('/remove_task')
def remove_task():
    # receive a standard task json
    task_name = request.GET.get('name')
    ok = app.wc.remove_task(task_name)
    return {'ok': ok}


if __name__ == "__main__":
    app.run()
