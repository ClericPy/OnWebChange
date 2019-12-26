#! coding: utf-8
import asyncio
import json
import os
import pathlib
import re
import time
from functools import partial
from inspect import getsource
from threading import Lock

import requests
from torequests.dummy import Requests
from torequests.logs import init_logger
from torequests.utils import curlparse, find_one, flush_print, md5, ttime

# 140 like weibo
SHORTEN_RESULT_MAX_LENGTH = 140
GLOBAL_LOCK = Lock()
__version__ = '0.2.6'


def _default_shorten_result_function(result):
    string = str(result)
    if len(string) < SHORTEN_RESULT_MAX_LENGTH:
        return string.strip()
    else:
        # 32bit md5
        return md5(result)


class WatchdogTask(object):
    logger = init_logger('WatchdogTask')
    req = None
    # frequency format: (concurrent_count, interval)
    DEFAULT_HOST_FREQUENCY = (1, 1)
    CHROME_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36'
    # reset the default `shorten_result_function`
    BeautifulSoup = None
    BeautifulSoupFeatures = 'html.parser'
    Tree = None
    GLOBAL_TIMEOUT = 10
    GLOBAL_RETRY = 3

    def __init__(self,
                 name,
                 request_args,
                 parser_name=None,
                 operation=None,
                 value=None,
                 tag='default',
                 work_hours='0, 24',
                 sorting_list=True,
                 check_interval=300,
                 last_check_time=None,
                 max_change=1,
                 check_result_list=None,
                 origin_url=None,
                 encoding=None,
                 last_change_time=None,
                 **nonsense_kwargs):
        """Watchdog task.
            :param name: Task name.
            :type name: str
            :param request_args: arg for sending a request, could be url/curl_string/dict.
            :type request_args: dict / str
            :param parser_name: re, css, json, python, defaults to None, use the resp.text.
            :type parser_name: str, optional
            :param operation: parse operation for the parser_name, defaults to None
            :type operation: str, optional
            :param value: value operation for the parser, defaults to None
            :type value: str, optional
            :param tag: tag for filter, defaults to "default"
            :type tag: str, optional
            :param work_hours: work_hours of the crawler, defaults to '0, 24', means range(0, 24)
            :type work_hours: str, optional
            :param sorting_list: whether sorting the list of result from `css or other parsers`, defaults to True
            :type sorting_list: bool, optional
            :param check_interval: check_interval, defaults to 300 seconds
            :type check_interval: int, optional
            :param last_check_time: last checking ttime like 2019-08-23 19:29:14, defaults to None
            :type last_check_time: str, optional
            :param max_change: save result in check_result_list, save the latest 5 change, defaults to 5
            :type max_change: list, optional
            :param check_result_list: latest `max_change` checking result, usually use md5 to shorten it, defaults to None
            :type check_result_list: list, optional
            :param origin_url: the url to see the changement, defaults to request_args['url']
            :type origin_url: str, optional

            request_args examples:
                url:
                    http://pypi.org
                args:
                    {'url': 'http://pypi.org', 'method': 'get'}
                curl:
                    curl 'https://pypi.org/' -H 'authority: pypi.org' -H 'cache-control: max-age=0' -H 'upgrade-insecure-requests: 1' -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36' -H 'sec-fetch-mode: navigate' -H 'sec-fetch-user: ?1' -H 'dnt: 1' -H 'accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3' -H 'sec-fetch-site: none' -H 'accept-encoding: gzip, deflate, br' -H 'accept-language: zh-CN,zh;q=0.9' -H 'cookie: user_id__insecure=; session_id=' --compressed

            parser examples:
                re:
                    operation = '.*?abc'
                    value = '$0' (or '$1', `$` means the group index for regex result)
                css:
                    operation = ".className"
                    value = '$string'
                        $string: return [node] as outer html
                        $text: return [node.text]
                        $get_text: return [node.get_text()]
                        @attr: [get attribute from node]
                json:
                    view more: https://github.com/adriank/ObjectPath
                    # input response JSON string: {"a": 1}
                    operation = "$.a"
                    value = None

                python:
                    ! function name should always be `parse` if value is None,
                        or use `value` as the function name.
                    `operation can be a function object.`
                    operation = r'''
                    def parse(resp):
                        return md5(resp.text)
                    '''
                    value = None
        """
        self.name = str(name)
        self.request_args = self._ensure_request_args(request_args)
        self.parser_name = parser_name
        self.operation = operation
        self.value = value
        self.tag = tag
        self.work_hours = self.ensure_work_hours(work_hours)
        self.check_interval = int(check_interval)
        self.sorting_list = sorting_list
        self.last_check_time = last_check_time
        self.max_change = int(max_change)
        self.last_change_time = last_change_time or ttime(0)
        # check_result_list: [{'data': 'xxx', 'time': '2019-08-23 19:27:20'}]
        if isinstance(check_result_list, str):
            check_result_list = json.loads(check_result_list)
        self.check_result_list = check_result_list or []
        self.origin_url = origin_url or self.request_args['url']
        self.encoding = encoding or None
        self.update_last_change_time()
        self.ensure_req()

    @classmethod
    def ensure_req(cls):
        if not cls.req:
            cls.req = Requests(
                default_host_frequency=cls.DEFAULT_HOST_FREQUENCY)

    @staticmethod
    def ensure_work_hours(work_hours):
        try:
            whs = json.loads(work_hours or "0, 24")
            for wh in whs:
                if not isinstance(wh, int):
                    break
            else:
                # good json-like int list
                return work_hours
            # bad json
            return '0, 24'
        except json.JSONDecodeError:
            work_hours = re.findall(r'\d+', work_hours or '0, 24')[:2]
            return ', '.join(work_hours)
        except Exception:
            return '0, 24'

    def check_work_hours(self, current_hour=None):
        current_hour = current_hour or int(time.strftime('%H'))
        if re.match(r'^\d+, \d+$', self.work_hours):
            return current_hour in range(*(
                int(i) for i in self.work_hours.split(', ')))
        else:
            return current_hour in json.loads(self.work_hours)

    @property
    def is_finished(self):
        return len(self.check_result_list) >= self.max_change

    def update_last_change_time(self):
        self.last_change_time = ttime(0)
        for item in self.check_result_list:
            if item['time'] > self.last_change_time:
                self.last_change_time = item['time']
        return self.last_change_time

    def _default_parser(self, resp):
        if resp:
            return resp.text
        else:
            self.logger.error(
                f'[{self.name}] request fail: [{getattr(resp, "status_code", -1)}], {resp.url}\n{resp.text.strip()[:200]} ...'
            )
            return ''

    def _re_parser(self, resp):
        if resp:
            scode = resp.content.decode(
                self.encoding, errors='ignore') if self.encoding else resp.text
            result = find_one(self.operation, scode)
            if not (isinstance(self.value, str) and self.value.startswith('$')):
                raise ValueError(
                    f'value should be string startswith `$`, like $1, $0, but {self.value} given.'
                )
            index = int(self.value[1:])
            return result[index]
        else:
            self.logger.error(
                f'[{self.name}] request fail: [{getattr(resp, "status_code", -1)}], {resp.url}\n{resp.text.strip()[:200]} ...'
            )
            return ''

    def _css_parser(self, resp):
        if not self.BeautifulSoup:
            from bs4 import BeautifulSoup
            self.__class__.BeautifulSoup = BeautifulSoup
        if resp:
            result = []
            scode = resp.content.decode(
                self.encoding, errors='ignore') if self.encoding else resp.text
            soup = self.BeautifulSoup(
                scode, features=self.BeautifulSoupFeatures)
            result = soup.select(self.operation)
            if self.value == '$text':
                result = [item.text for item in result]
            elif self.value == '$get_text':
                result = [item.get_text() for item in result]
            elif not self.value or self.value == '$string':
                result = [str(item) for item in result]
            elif self.value.startswith('@'):
                result = [item.get(self.value[1:], '') for item in result]
                # for class always be seen as list
                result = [
                    ' '.join(item) if isinstance(item, list) else item
                    for item in result
                ]
            # ensure the plain sequence
            if self.sorting_list:
                result = sorted([(item or '').strip() for item in result])
            return result
        else:
            self.logger.error(
                f'[{self.name}] request fail: [{getattr(resp, "status_code", -1)}], {resp.url}\n{resp.text.strip()[:200]} ...'
            )
            return ''

    def _python_parser(self, resp):
        if resp:
            if callable(self.operation):
                parse_function = self.operation
            else:
                if not isinstance(self.operation, str):
                    raise ValueError(
                        f'self.operation expect type str, but {type(self.operation)} given.'
                    )
                self.operation = self.operation.strip()
                exec(self.operation)
                function = locals().get(self.value or 'parse')
                if function:
                    self._python_parser_function = function
                else:
                    raise ValueError(
                        f'invalid function code from operation, function name should be parse: {self.operation}'
                    )
                parse_function = self._python_parser_function
            result = parse_function(resp)
            return result
        else:
            self.logger.error(
                f'[{self.name}] request fail: [{getattr(resp, "status_code", -1)}], {resp.url}\n{resp.text.strip()[:200]} ...'
            )
            return ''

    def _json_parser(self, resp):
        if resp:
            try:
                json_object = json.loads(resp.content)
            except json.JSONDecodeError:
                self.logger.error('')
                return ''
            if not self.Tree:
                from objectpath import Tree
                self.__class__.Tree = Tree
            tree = self.Tree(json_object)
            result = tree.execute(self.operation)
            return result
        else:
            self.logger.error(
                f'[{self.name}] request fail: [{getattr(resp, "status_code", -1)}], {resp.url}\n{resp.text.strip()[:200]} ...'
            )
            return ''

    def _ensure_parser(self, parser_name):
        parsers = {
            're': self._re_parser,
            'css': self._css_parser,
            'python': self._python_parser,
            'json': self._json_parser,
        }
        return parsers.get(parser_name, self._default_parser)

    def _ensure_request_args(self, request_args):
        if not request_args:
            raise ValueError('request_args should not be null')
        if isinstance(request_args, str):
            request_args = request_args.strip()
            if request_args.startswith('http'):
                return {
                    'url': request_args,
                    'method': 'get',
                    'headers': {
                        'User-Agent': self.CHROME_UA
                    }
                }
            elif request_args.startswith('curl'):
                return curlparse(request_args)
            elif request_args.startswith('{'):
                return json.loads(request_args)
            else:
                raise ValueError(
                    'request_args string should be a curl string or url')
        elif isinstance(request_args, dict):
            return request_args
        else:
            raise ValueError(
                f'please ensure your arg as str(startswith `http` or `curl`) / dict: {request_args}'
            )

    async def get_resp(self):
        resp = await self.req.request(
            retry=self.GLOBAL_RETRY,
            timeout=self.GLOBAL_TIMEOUT,
            verify=0,
            **self.request_args)
        return resp

    def get_parse_result(self, resp):
        parser = self._ensure_parser(self.parser_name)
        result = parser(resp)
        return result

    async def fetch_once(self):
        resp = await self.get_resp()
        if not resp:
            error = f'{self.name} request failed: {resp.text}'
            self.logger.error(error)
            raise requests.HTTPError(error)
        result = self.get_parse_result(resp)
        return result

    async def test(self):
        result = await self.fetch_once()
        return result

    def sync_test(self):
        resp = requests.request(verify=0, **self.request_args)
        result = self.get_parse_result(resp)
        return result

    def _ensure_function_code(self, func):
        if not func:
            return None
        if callable(func):
            return getsource(func)
        else:
            return str(func)

    def __str__(self):
        return f'<WatchdogTask {self.name}>'

    def to_json(self, **kwargs):
        return json.dumps(self.to_dict(), **kwargs)

    def to_dict(self):
        return {
            'name': self.name,
            'request_args': self.request_args,
            'parser_name': self.parser_name,
            'operation': self.operation,
            'value': self.value,
            'tag': self.tag,
            'work_hours': self.work_hours,
            'check_interval': self.check_interval,
            'sorting_list': self.sorting_list,
            'last_check_time': self.last_check_time,
            'check_result_list': self.check_result_list,
            'max_change': self.max_change,
            'origin_url': self.origin_url,
            'encoding': self.encoding,
            'last_change_time': self.last_change_time
        }

    def dump_task(self):
        """Dump task info into JSON string.
        """
        return self.to_json()

    @classmethod
    def load_task(cls, json_or_dict):
        if isinstance(json_or_dict, str):
            json_or_dict = json.loads(json_or_dict)
        return cls(**json_or_dict)


class WatchdogCage(object):
    logger = init_logger('WatchdogCage')

    def __init__(self,
                 file_path=None,
                 shorten_result_function=None,
                 auto_save=True,
                 loop_interval=300,
                 pretty_json=True,
                 change_callback=None,
                 loop=None,
                 quota=20):
        self.file_path = file_path or self.default_file_path
        # self.tasks: dict with key=task_name, value=WatchdogTask obj
        self.tasks = self.load_tasks_from_file(self.file_path)
        self.shorten_result_function = shorten_result_function or _default_shorten_result_function
        self.auto_save = auto_save
        self.loop_interval = loop_interval
        self.pretty_json = pretty_json
        self.change_callback = change_callback
        self.loop = loop
        self.quota = quota
        self._force_crawl = False

    def check_quota(self):
        if len(self.tasks) >= self.quota:
            raise IOError(
                f'The quota has been exceeded {len(self.tasks)} / {self.quota}.'
            )

    @classmethod
    def refresh_file_path(cls, file_path):
        cls.logger.info(f'refreshing json file {file_path}.')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('{}')

    @classmethod
    def backup_file_path(cls, file_path):
        with open(f'{file_path}.backup', 'wb') as f_write, open(
                file_path, 'rb') as f_read:
            f_write.write(f_read.read())

    @property
    def default_file_path(self):
        dir_path = pathlib.Path(os.path.expanduser("~")) / "watch_dog_cage"
        file_path = dir_path / 'default_tasks.json'
        self.logger.info(f'using default_file_path: {file_path}')
        if not dir_path.is_dir():
            self.logger.warning(f'`{dir_path}` directory not found. mkdir...')
            dir_path.mkdir()
        if not (file_path.is_file() and file_path.stat().st_size):
            self.logger.warning(f'`{file_path}` is null, rewriting it.')
            self.refresh_file_path(file_path)
        return str(file_path)

    def check_auto_save(self):
        if self.auto_save:
            self.save_tasks()

    def add_task(self, task):
        self.check_quota()
        if task.name in self.tasks:
            self.logger.error(f'{task} has existed, please rename/remove it.')
            return False
        self.tasks[task.name] = task
        self.check_auto_save()
        return True

    def update_task(self, task):
        self.check_quota()
        ok = task.name in self.tasks
        self.tasks[task.name] = task
        self.check_auto_save()
        return ok

    def remove_task(self, task_name):
        is_exist = bool(self.tasks.pop(task_name, None))
        if is_exist:
            self.check_auto_save()
        return task_name not in self.tasks

    def get_task(self, task_name=None):
        if task_name:
            task = self.tasks.get(task_name)
            if task:
                return task.to_dict()
        else:
            return self.tasks_dict

    @property
    def tasks_dict(self):
        return {task.name: task.to_dict() for task in self.tasks.values()}

    def save_tasks(self, file_path=None):
        with GLOBAL_LOCK:
            file_path = file_path or self.file_path
            with open(file_path, 'w', encoding='utf-8') as f:
                if self.pretty_json:
                    json.dump(self.tasks_dict, f, ensure_ascii=False, indent=2)
                else:
                    json.dump(self.tasks_dict, f)

    @staticmethod
    def load_tasks_from_file(file_path):
        with GLOBAL_LOCK:
            with open(file_path, encoding='utf-8') as f:
                tasks_dict = {
                    task_name: WatchdogTask.load_task(task_json)
                    for task_name, task_json in json.load(f).items()
                }
            return tasks_dict

    async def run_task(self, task):
        try:
            result = await task.fetch_once()
        except requests.HTTPError as err:
            return err
        if result:
            shorten_result = self.shorten_result_function(result)
        else:
            shorten_result = 'No result.'
        exist_results = {item['data'] for item in task.check_result_list}
        # if shorten_result not exist, insert into check_result_list
        if shorten_result not in exist_results:
            task.check_result_list.insert(0, {
                'data': shorten_result,
                'time': ttime()
            })
            state = f'task [{task.name}] has new change [{len(task.check_result_list)}/{task.max_change}] => `{shorten_result}`'
            task.update_last_change_time()
            if self.change_callback:
                if asyncio.iscoroutinefunction(self.change_callback):
                    await self.change_callback(task)
                elif callable(self.change_callback):
                    await self.loop.run_in_executor(None, self.change_callback,
                                                    task)
                else:
                    self.logger.error(
                        f'bad change_callback type: {type(self.change_callback)}, should be function/coroutinefunction'
                    )
        else:
            state = ''
        task.check_result_list = task.check_result_list[:task.max_change]
        task.last_check_time = ttime()
        return state

    async def run(self):
        self.logger.info(f'{len(self.tasks)} tasks start running.')
        WatchdogTask.ensure_req()
        while 1:
            changes = []
            ttime_0 = ttime(0)
            if self._force_crawl:
                for task in self.tasks.values():
                    task.last_check_time = '2000-01-01 00:00:00'
                self._force_crawl = False
            current_hour = int(time.strftime('%H'))
            running_tasks = [
                asyncio.ensure_future(self.run_task(task))
                for task in self.tasks.values()
                if task.check_work_hours(current_hour=current_hour) and
                ttime(time.time() - task.check_interval) >
                (task.last_check_time or ttime_0)
            ]
            self.logger.info(
                f'{len(running_tasks)} tasks checking for interval overdue.')
            for task in running_tasks:
                state = await task
                changes.append(state)
            self.save_tasks()
            for change in changes:
                if change:
                    self.logger.info(change)
            for _ in range(int(self.loop_interval) + 1, 0, -1):
                await asyncio.sleep(1)
                flush_print(_, sep="", end=" ")
                if self._force_crawl:
                    self.logger.info('crawl for force_crawl')
                    break
            flush_print()

        self.logger.info('no tasks remaining.')

    def __del__(self):
        self.logger.info('stop running.')

    def __str__(self):
        tasks_set = {str(task) for task in self.tasks.values()}
        return str(tasks_set)


class WebHandler(object):
    logger = init_logger('WebHandler')
    VUE_JS_CDN = 'https://cdn.staticfile.org/vue/2.6.10/vue.min.js'
    ELEMENT_CSS_CDN = 'https://cdn.staticfile.org/element-ui/2.11.1/theme-chalk/index.css'
    ELEMENT_JS_CDN = 'https://cdn.staticfile.org/element-ui/2.11.1/index.js'
    VUE_RESOURCE_CDN = 'https://cdn.staticfile.org/vue-resource/1.5.1/vue-resource.min.js'

    def __init__(self,
                 app,
                 file_path=None,
                 shorten_result_function=None,
                 auto_save=True,
                 loop_interval=300,
                 pretty_json=True,
                 auto_open_browser=True,
                 change_callback=None,
                 app_kwargs=None,
                 username='',
                 password=''):
        self.app_kwargs = app_kwargs or {}
        self.host = self.app_kwargs.get('host', '127.0.0.1')
        self.port = self.app_kwargs.get('port', 9988)
        self.loop = asyncio.get_event_loop()
        self.wc = WatchdogCage(
            file_path=file_path,
            shorten_result_function=shorten_result_function,
            auto_save=auto_save,
            loop_interval=loop_interval,
            pretty_json=pretty_json,
            change_callback=change_callback,
            loop=self.loop)
        self.wc.username = username
        self.wc.password = password
        app.wc = self.wc
        app.logger = self.logger
        app.loop_interval = loop_interval
        app.lock = GLOBAL_LOCK
        app.cdn_urls = dict(
            VUE_JS_CDN=self.VUE_JS_CDN,
            ELEMENT_CSS_CDN=self.ELEMENT_CSS_CDN,
            ELEMENT_JS_CDN=self.ELEMENT_JS_CDN,
            VUE_RESOURCE_CDN=self.VUE_RESOURCE_CDN,
        )
        app.pid = os.getpid()
        app.console_url = self.console_url
        self.app = app
        self.auto_open_browser = auto_open_browser

    @property
    def console_url(self):
        return f'http://{self.host}:{self.port}'

    async def run_server(self):
        # http://127.0.0.1:9988/

        self.logger.info(
            f'run_server with kwargs: {self.app_kwargs}, console_url: {self.console_url}'
        )
        self.loop.run_in_executor(None, partial(self.app.run,
                                                **self.app_kwargs))
        if self.auto_open_browser:
            import webbrowser
            webbrowser.open(self.console_url)

        await asyncio.ensure_future(self.wc.run())

    def run(self):
        self.loop.run_until_complete(self.run_server())
