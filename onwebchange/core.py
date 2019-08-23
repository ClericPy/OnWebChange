import asyncio
import json
import os
import pathlib
from inspect import getsource

from torequests.dummy import Requests
from torequests.logs import init_logger
from torequests.utils import curlparse, find_one, md5, ttime


def _default_shorten_result_function(result):
    string = str(result)
    if len(string) < 50:
        return string
    else:
        # 32bit md5
        return md5(result)


class WatchdogTask(object):
    logger = init_logger('WatchdogTask')
    req = None
    DEFAULT_HOST_FREQUENCY = (1, 1)
    CHROME_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36'
    # frequency format: (concurrent_count, interval)
    # req.set_frequency('pypi.org', 1, 3)
    # reset the default `shorten_result_function`
    BeautifulSoup = None
    BeautifulSoupFeatures = 'html.parser'
    Tree = None
    GLOBAL_TIMEOUT = 10
    GLOBAL_RETRY = 10

    def __init__(self,
                 name,
                 request_args,
                 parser_name=None,
                 operation=None,
                 value=None,
                 sorting_list=True,
                 check_interval=60,
                 last_check_time=None,
                 max_change=2,
                 check_result_list=None,
                 origin_url=None):
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
            :param sorting_list: whether sorting the list of result from `css or other parsers`, defaults to True
            :type sorting_list: bool, optional
            :param check_interval: check_interval, defaults to 60 seconds
            :type check_interval: int, optional
            :param last_check_time: last checking ttime like 2019-08-23 19:29:14, defaults to None
            :type last_check_time: str, optional
            :param max_change: save result in check_result_list, save the latest 2 change, defaults to 2
            :type max_change: list, optional
            :param check_result_list: latest `max_change` checking result, usually use md5 to shorten it, defaults to None
            :type check_result_list: list, optional
            :param origin_url: load the url to see the changement.
            :type origin_url: str, optional

            request_args examples:
                url:
                    http://pypi.org
                args:
                    {'url': 'http://pypi.org', 'method': 'get'}
                curl:
                    r'''curl 'https://pypi.org/' -H 'authority: pypi.org' -H 'cache-control: max-age=0' -H 'upgrade-insecure-requests: 1' -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36' -H 'sec-fetch-mode: navigate' -H 'sec-fetch-user: ?1' -H 'dnt: 1' -H 'accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3' -H 'sec-fetch-site: none' -H 'accept-encoding: gzip, deflate, br' -H 'accept-language: zh-CN,zh;q=0.9' -H 'cookie: user_id__insecure=; session_id=' --compressed'''

            parser examples:
                re:
                    operation = 'None'
                    value = '$0' (or '$1', `$` means the group num for regex result)
                css:
                    operation = ".className"
                    value = '$string'
                        $string: return str(node) as outer html
                        $text: return node.text
                        $get_text: return node.get_text()
                        @attr: get attr from node
                json:
                    view more: https://github.com/adriank/ObjectPath
                    input response JSON string: {"a": 1}
                    operation = "$.a"
                    value = None

                python:
                    ! function name should always be `parse` if value is None,
                        or use `value` as the function name.
                    `operation can be a function object.`
                    operation = lambda resp: resp.text
                    operation = r'''
                    def parse(resp):
                        return md5(resp.text)
                    '''
                    value = None
        """
        self.name = name
        self.request_args = self._ensure_request_args(request_args)
        self.parser_name = parser_name
        self.operation = operation
        self.value = value
        self.check_interval = check_interval
        self.sorting_list = sorting_list
        self.last_check_time = last_check_time
        self.max_change = max_change
        # check_result_list: [{'data': 'xxx', 'time': '2019-08-23 19:27:20'}]
        self.check_result_list = check_result_list or []
        self.origin_url = origin_url
        self.update_last_change_time()
        if not self.req:
            self.__class__.req = Requests(
                default_host_frequency=self.DEFAULT_HOST_FREQUENCY)

    @property
    def finished(self):
        return len(self.check_result_list) >= self.max_change

    def update_last_change_time(self):
        self.last_change_time = ttime(0)
        for item in self.check_result_list:
            if item['time'] > self.last_change_time:
                self.last_change_time = item['data']
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
            result = find_one(self.operation, resp.text)
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
            soup = self.BeautifulSoup(
                resp.text, features=self.BeautifulSoupFeatures)
            result = soup.select(self.operation)
            if self.value == '$text':
                return ''.join([item.text for item in result])
            elif self.value == '$get_text':
                return ''.join([item.get_text() for item in result])
            elif not self.value or self.value == '$string':
                return ''.join([str(item) for item in result])
            elif self.value.startswith('@'):
                result = [item.get(self.value[1:], '') for item in result]
                # for class always be seen as list
                result = [
                    ' '.join(item) if isinstance(item, list) else item
                    for item in result
                ]
                # ensure the plain sequence
                if self.sorting_list:
                    result = sorted(result)
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
            **self.request_args)
        return resp

    def get_parse_result(self, resp):
        parser = self._ensure_parser(self.parser_name)
        result = parser(resp)
        return result

    async def fetch_once(self):
        resp = await self.get_resp()
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
            'check_interval': self.check_interval,
            'sorting_list': self.sorting_list,
            'last_check_time': self.last_check_time,
            'check_result_list': self.check_result_list,
            'origin_url': self.origin_url,
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
                 loop_interval=60,
                 pretty_json=True):
        self.file_path = file_path or self.default_file_path
        # self.tasks: dict with key=task_name, value=WatchdogTask obj
        self.tasks = self.load_tasks(self.file_path)
        self.shorten_result_function = shorten_result_function or _default_shorten_result_function
        self.auto_save = auto_save
        self.loop_interval = loop_interval
        self.pretty_json = pretty_json

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
        if task.name in self.tasks:
            self.logger.error(f'{task} has existed, please rename/remove it.')
            return False
        self.tasks[task.name] = task
        self.check_auto_save()
        return True

    def update_task(self, task):
        ok = task.name in self.tasks
        self.tasks[task.name] = task
        self.check_auto_save()
        return ok

    def remove_task(self, task_name):
        ok = bool(self.tasks.pop(task_name, None))
        if ok:
            self.check_auto_save()
        return ok

    def get_task(self, task_name):
        return self.tasks.pop(task_name, None)

    def save_tasks(self, file_path=None):
        file_path = file_path or self.file_path
        tasks = {task.name: task.to_dict() for task in self.tasks.values()}
        with open(file_path, 'w') as f:
            if self.pretty_json:
                json.dump(tasks, f, ensure_ascii=False, indent=2)
            else:
                json.dump(tasks, f)

    @staticmethod
    def load_tasks(file_path):
        with open(file_path) as f:
            tasks_dict = {
                task_name: WatchdogTask.load_task(task_json)
                for task_name, task_json in json.load(f).items()
            }
        return tasks_dict

    async def run_task(self, task):
        print(1111111111111, flush=1)
        result = await task.fetch_once()
        print(2222, flush=1)
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
            state = f'{task.name} has new change [{len(task.check_result_list)}/{task.max_change}] => {shorten_result}'
            task.update_last_change_time()
        else:
            state = ''
        task.check_result_list = task.check_result_list[:task.max_change]
        return state

    async def run(self):
        self.logger.info(f'{len(self.tasks)} tasks start running.')
        while self.tasks:
            changes = []
            for task in self.tasks.values():
                state = await self.run_task(task)
                changes.append(state)
            self.save_tasks()
            for change in changes:
                if change:
                    self.logger.info(change)
            await asyncio.sleep(self.loop_interval)
        self.logger.info('no tasks remaining.')

    def __del__(self):
        self.logger.info('stop running.')

    def __str__(self):
        tasks_set = {str(task) for task in self.tasks.values()}
        return tasks_set


async def test_wc():
    wc = WatchdogCage()
    task = WatchdogTask('test_json', 'http://baidu.com', 're', '.{,5}"', '$0')
    wc.add_task(task)
    task = WatchdogTask('test_re', 'https://p.3.cn', 're', '.{,5}"', '$0')
    wc.add_task(task)
    task = WatchdogTask('test_json2', 'http://qq.com', 're', '.{,5}"', '$0')
    wc.add_task(task)
    task = WatchdogTask('test_re2', 'https://httpbin.org/get', 're', '.{,5}"', '$0')
    wc.add_task(task)
    await wc.run()


def test_in_threa():
    asyncio.run(test_wc())


if __name__ == "__main__":
    from threading import Thread
    t = Thread(target=test_in_threa)
    t.start()
    t.join()
