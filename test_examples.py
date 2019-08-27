from onwebchange.core import WatchdogTask, WatchdogCage
import asyncio
loop = asyncio.get_event_loop()


async def _test_task_css_parser():
    # test css selector get attr
    task = WatchdogTask('test_css', 'https://pypi.org', 'css',
                        '.lede-paragraph', '@class')
    resp = await task.get_resp()
    result = task.get_parse_result(resp)
    assert result == ['lede-paragraph']
    # test css selector outer-html
    task.value = '$string'
    result = task.get_parse_result(resp)
    assert result == [
        '<p class="lede-paragraph">The Python Package Index (PyPI) is a repository of software for the Python programming language.</p>'
    ]
    # test css selector text
    task.value = '$text'
    result = task.get_parse_result(resp)
    assert result == [
        'The Python Package Index (PyPI) is a repository of software for the Python programming language.'
    ]
    # test css selector text content
    task.value = '$get_text'
    result = task.get_parse_result(resp)
    assert result == [
        'The Python Package Index (PyPI) is a repository of software for the Python programming language.'
    ]


async def _test_task_re_parser():
    # test regex group 1
    task = WatchdogTask('test_re', 'https://pypi.org', 're',
                        'class="(lede-paragraph)"', '$1')
    resp = await task.get_resp()
    result = task.get_parse_result(resp)
    assert result == 'lede-paragraph'
    # test regex matched sub-string
    task.value = '$0'
    result = task.get_parse_result(resp)
    assert result == 'class="lede-paragraph"'


async def _test_task_python_parser():

    def get_prefix_text(resp):
        return resp.text.strip()[:30]

    # test python function object as operation
    task = WatchdogTask('test_python', 'https://pypi.org', 'python',
                        get_prefix_text)
    resp = await task.get_resp()
    result = task.get_parse_result(resp)
    # test python function code string as operation
    assert result == r'''<!DOCTYPE html>
<html lang="en'''
    task.operation = r'''
def parse(resp):
    return str(resp.status_code)
'''
    result = task.get_parse_result(resp)
    assert result == '200'


async def _test_task_json_parser():
    # test regex group 1
    task = WatchdogTask('test_json', 'http://httpbin.org/get', 'json', '$.url')
    resp = await task.get_resp()
    result = task.get_parse_result(resp)
    assert result == 'https://httpbin.org/get'


async def _test_dump_load_task():
    task1 = WatchdogTask('test_json', 'http://httpbin.org/get', 'json', '$.url')
    task1_json = task1.dump_task()
    # {"name": "test_json", "request_args": {"url": "http://httpbin.org/get", "method": "get"}, "parser_name": "json", "operation": "$.url", "value": null, "interval": 60, "sorting_list": true, "change_callback": null}
    # task2 = WatchdogTask(**task1.to_dict())
    task2 = WatchdogTask.load_task(task1_json)
    r = await task2.get_resp()
    result = task2.get_parse_result(r)
    assert result == 'https://httpbin.org/get'


def test_task_css_parser():
    loop.run_until_complete(_test_task_css_parser())


def test_task_re_parser():
    loop.run_until_complete(_test_task_re_parser())


def test_task_python_parser():
    loop.run_until_complete(_test_task_python_parser())


def test_task_json_parser():
    loop.run_until_complete(_test_task_json_parser())


def test_dump_load_task():
    loop.run_until_complete(_test_dump_load_task())


if __name__ == "__main__":
    test_task_css_parser()
    test_task_re_parser()
    test_task_python_parser()
    test_task_json_parser()
    test_dump_load_task()
