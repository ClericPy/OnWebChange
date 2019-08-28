# onwebchange

### Install

> pip install onwebchange -U



### Requirements

> torequests
> click
> bottle
> objectpath
> beautifulsoup4



### Default Web UI

![demo](demo.png)



### example

> python3 -m onwebchange -f wc.config -i 300 -a

or

```python
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
    # python3 -m onwebchange -f wc.config -i 300 -a
    wh.run()

```



### New Task template

```python
  "name": "task name0",
  "request_args": "https://pypi.org", # could be url, curl string, request args dict.
  "parser_name": "css", # could be re/css/json/python
  "operation": ".lede-paragraph",
  "value": "$text",
  "check_interval": 300,
  "max_change": 2,
  "sorting_list": true,
  "origin_url": "https://pypi.org",
  "encoding": null
{
  "name": "task name1",
  "request_args": "https://pypi.org",
  "parser_name": "re",
  "operation": "class=\"(lede-paragraph)\"",
  "value": "$1",
  "check_interval": 300,
  "max_change": 2,
  "sorting_list": true,
  "origin_url": "",
  "encoding": null
}
{
  "name": "task name2",
  "request_args": "http://httpbin.org/get",
  "parser_name": "json",
  "operation": "$.url",
  "value": "",
  "check_interval": 300,
  "sorting_list": true,
  "origin_url": "",
  "encoding": null
}
```

### More docs
```python

Watchdog task.
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
            :param max_change: save result in check_result_list, save the latest 2 change, defaults to 2
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
                    operation = lambda resp: resp.text
                    operation = r'''
                    def parse(resp):
                        return md5(resp.text)
                    '''
                    value = None
```
