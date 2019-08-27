#! coding: utf-8

import os
import pathlib
import traceback

from bottle import Bottle, request, template
from torequests.utils import ptime, time, timeago

from .core import GLOBAL_LOCK, WatchdogTask

# app.wc = xxx
app = Bottle()
index_tpl_path = str(pathlib.Path(__file__).parent / 'views').replace(
    '\\', '/') + '/index.html'


@app.get('/')
def index():
    return template(
        index_tpl_path, cdn_urls=app.cdn_urls, loop_interval=app.loop_interval)


@app.get('/shutdown')
def shutdown():
    with GLOBAL_LOCK:
        app.logger.warning('shuting down.')
        os.kill(app.pid, 9)


@app.get('/get_task')
def get_task():
    task_name = request.GET.get('name')
    return app.wc.get_task(task_name)


@app.get('/get_task_list')
def get_task_list():
    task_name = request.GET.get('name')
    result = app.wc.get_task(task_name)
    result_list = sorted(
        result.values(),
        key=lambda item: item.get('last_change_time', '2000-01-01 00:00:00'),
        reverse=True)
    for item in result_list:
        item['latest_data'] = item['check_result_list'][0]['data'] if item[
            'check_result_list'] else ''
        item['change_time_ago'] = '{} ago'.format(
            timeago(
                time.time() - ptime(item['check_result_list'][0]['time']),
                accuracy=1,
                format=1)) if item['check_result_list'] else ''
    return {'ok': True, 'tasks': result_list}


@app.post('/update_task')
def update_task():
    # receive a standard task json
    task_json = request.json
    try:
        task = WatchdogTask.load_task(task_json)
        ok = app.wc.update_task(task)
    except Exception:
        app.wc.logger.error(traceback.format_exc())
        ok = False
    return {'ok': ok}


@app.get('/remove_task')
def remove_task():
    # receive a standard task json
    task_name = request.GET.get('name')
    if task_name:
        task_name = task_name.encode('latin-1').decode('utf-8')
    ok = app.wc.remove_task(task_name)
    return {'ok': ok}


if __name__ == "__main__":
    app.run()
