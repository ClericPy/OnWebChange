#! coding: utf-8

import os
import pathlib
import traceback

from bottle import Bottle, request, response, template
from torequests.utils import escape, ptime, time, timeago, ttime

from .core import GLOBAL_LOCK, WatchdogTask

# app.wc = xxx
app = Bottle()
index_tpl_path = str(pathlib.Path(__file__).parent / 'templates').replace(
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


@app.post('/test_task')
def test_task():
    # receive a standard task json
    task_json = request.json
    try:
        task = WatchdogTask.load_task(task_json)
        result = task.sync_test()
        ok = True
    except Exception as e:
        app.wc.logger.error(traceback.format_exc())
        ok = False
        result = str(e)
    return {'result': result, 'ok': ok}


@app.get('/remove_task')
def remove_task():
    # receive a standard task json
    task_name = request.GET.get('name')
    if task_name:
        task_name = task_name.encode('latin-1').decode('utf-8')
    ok = app.wc.remove_task(task_name)
    return {'ok': ok}


def gen_rss(data):
    nodes = []
    channel = data['channel']
    channel_title = channel['title']
    channel_desc = channel['description']
    channel_link = channel['link']
    channel_language = channel.get('language', 'zh-cn')
    item_keys = ['title', 'description', 'link', 'guid', 'pubDate']
    for item in data['items']:
        item_nodes = []
        for key in item_keys:
            value = item.get(key)
            if value:
                item_nodes.append(f'<{key}>{escape(value)}</{key}>')
        nodes.append(''.join(item_nodes))
    items_string = ''.join((f'<item>{tmp}</item>' for tmp in nodes))
    return rf'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
  <title>{channel_title}</title>
  <link>{channel_link}</link>
  <description>{channel_desc}</description>
  <language>{channel_language}</language>
  {items_string}
</channel>
</rss>
'''


@app.get("/rss")
def rss_handler():
    lang = request.GET.get('lang') or 'zh-cn'
    xml_data: dict = {
        'channel': {
            'title': 'Watchdog',
            'description': 'Watchdog on web change',
            'link': app.console_url,
            'language': lang,
        },
        'items': []
    }
    t0 = ttime(0)
    for task in sorted(
            app.wc.tasks.values(),
            key=lambda item: item.last_change_time or t0,
            reverse=True):
        # 当日 0 点发布前一天的结果
        pubDate: str = ttime(
            ptime(task.last_change_time), fmt='%a, %d %b %Y %H:%M:%S')
        link: str = task.origin_url
        title: str = f'{task.name}#{task.last_change_time}'
        item: dict = {
            'title': title,
            'link': link,
            'guid': title,
            'pubDate': pubDate
        }
        xml_data['items'].append(item)
    xml: str = gen_rss(xml_data)
    response.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
    return xml.encode('utf-8')


if __name__ == "__main__":
    app.run()
