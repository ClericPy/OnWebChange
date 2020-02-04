# -*- coding: utf-8 -*-
import codecs
import sys

from onwebchange import __version__ as version
from setuptools import find_packages, setup
"""
linux:
rm -rf "dist/*";rm -rf "build/*";python3 setup.py bdist_wheel;twine upload "dist/*;rm -rf "dist/*";rm -rf "build/*""
win32:
rm -rf dist;rm -rf build;python3 setup.py bdist_wheel;twine upload "dist/*";rm -rf dist;rm -rf build;rm -rf onwebchange.egg-info
"""

install_requires = [
    'torequests', 'click', 'bottle', 'objectpath', 'beautifulsoup4'
]

if sys.version_info < (3, 6, 0):
    raise RuntimeError("aiohttp 3.x requires Python 3.6.0+")

with codecs.open("README.md", encoding="u8") as f:
    long_description = f.read()

setup(
    name="onwebchange",
    version=version,
    keywords=("watchdog web change."),
    description="watchdog toolkit for check web change.",
    long_description=long_description,
    long_description_content_type='text/markdown',
    license="MIT License",
    install_requires=install_requires,
    py_modules=["onwebchange"],
    author="ClericPy",
    author_email="clericpy@gmail.com",
    url="https://github.com/ClericPy/onwebchange",
    packages=find_packages(),
    platforms="any",
    package_data={'onwebchange': ['templates/*.html']},
    # include_package_data=True,
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
)
