#! coding: utf-8

import base64
import os
import pathlib
import traceback

from bottle import Bottle, request, response, template, HTTPError, redirect
from torequests.utils import escape, ptime, time, timeago, ttime, md5

from .core import GLOBAL_LOCK, WatchdogTask, __version__

# app.wc = xxx
app = Bottle()
index_tpl_path = str(pathlib.Path(__file__).parent / 'templates').replace(
    '\\', '/') + '/index.html'


def check_login(realm="private", text="Access denied"):

    def decorator(func):

        def wrapper(*a, **ka):
            if all((app.wc.username, app.wc.password)):
                username, password = request.auth or (None, None)
                if username != app.wc.username or password != app.wc.password:
                    err = HTTPError(401, text)
                    err.add_header('WWW-Authenticate',
                                   'Basic realm="%s"' % realm)
                    return err
            return func(*a, **ka)

        return wrapper

    return decorator


@app.get('/')
@check_login()
def index():
    tag = request.GET.get('tag') or ''
    return template(
        index_tpl_path,
        cdn_urls=app.cdn_urls,
        loop_interval=app.loop_interval,
        version=__version__,
        tag=tag)


@app.get('/shutdown')
@check_login()
def shutdown():
    with GLOBAL_LOCK:
        app.logger.warning('shuting down.')
        os.kill(app.pid, 9)


@app.get('/crawl_once')
@check_login()
def crawl_once():
    app.wc._force_crawl = True
    return {'ok': True}


@app.get('/get_task')
@check_login()
def get_task():
    task_name = request.GET.get('name')
    return app.wc.get_task(task_name)


@app.get('/get_task_list')
@check_login()
def get_task_list():
    task_name = request.GET.get('name')
    tag = request.GET.get('tag') or ''
    result = app.wc.get_task(task_name)
    all_tags = set()
    result_list = sorted(
        filter(lambda item: item.get('tag') == tag if (all_tags.add(item.get('tag'))) or tag else True, result.values()),
        key=lambda item: item.get('last_change_time', '2000-01-01 00:00:00'),
        reverse=True)
    all_tags = sorted(({'value': tag, 'label': tag} for tag in all_tags), key=lambda item: item['label'])
    all_tags.insert(0, {'value': '', 'label': 'All'})
    for item in result_list:
        item['latest_data'] = item['check_result_list'][0]['data'] if item[
            'check_result_list'] else ''
        item['change_time_ago'] = '{} ago'.format(
            timeago(
                time.time() - ptime(item['check_result_list'][0]['time']),
                accuracy=1,
                format=1)) if item['check_result_list'] else ''
    return {'ok': True, 'tasks': result_list, 'all_tags': all_tags}


@app.post('/update_task')
@check_login()
def update_task():
    # for add task or update task
    # receive a standard task json
    task_json = request.json
    result = {}
    try:
        task = WatchdogTask.load_task(task_json)
        ok = app.wc.update_task(task)
    except Exception as err:
        app.wc.logger.error(traceback.format_exc())
        ok = False
        result['error'] = err
    result['exist'] = ok
    return result


@app.post('/test_task')
@check_login()
def test_task():
    # receive a standard task json
    task_json = request.json
    try:
        task = WatchdogTask.load_task(task_json)
        result = task.sync_test()
    except Exception as e:
        app.wc.logger.error(traceback.format_exc())
        result = str(e)
    return result


@app.get('/remove_task')
@check_login()
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
  <image>
    <url>{channel_link}/icon.png</url>
    <title>{channel_title}</title>
    <link>{channel_link}</link>
    <width>32</width>
    <height>32</height>
   </image>
  {items_string}
</channel>
</rss>
'''


@app.get("/rss")
def rss_handler():
    lang = request.GET.get('lang') or 'zh-cn'
    tag = request.GET.get('tag') or ''
    token = request.GET.get('token')
    # redirect for token
    if all(
        (app.wc.username,
         app.wc.password)) and token != md5([app.wc.username, app.wc.password]):
        username, password = request.auth or (None, None)
        if username == app.wc.username or password == app.wc.password:
            token = md5([username, password])
            redirect(f'/rss?token={token}&tag={tag}', 302)
        else:
            redirect('/', 302)
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
        if tag and task.tag != tag:
            continue
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
    response.headers['Content-Type'] = 'text/xml; charset=utf-8'
    return xml.encode('utf-8')


@app.get("/icon.png")
@check_login()
def icon():
    response.headers['Content-Type'] = 'image/png'
    response.headers['Vary'] = 'Accept-Encoding'
    image_b64 = r'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'
    return base64.b64decode(image_b64)


if __name__ == "__main__":
    app.run()
