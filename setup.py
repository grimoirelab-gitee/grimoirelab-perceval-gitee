#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2019 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Authors:
#     Santiago Dueñas <sduenas@bitergia.com>
#     Jesus M. Gonzalez-Barahona <jgb@gsyc.es>
#

import codecs
import os.path
import sys
import unittest

from setuptools import setup, find_packages
from setuptools.command.test import test as TestClass

here = os.path.abspath(os.path.dirname(__file__))
readme_md = os.path.join(here, 'README.md')

# Get the package description from the README.md file
with codecs.open(readme_md, encoding='utf-8') as f:
    long_description = f.read()

version = '0.1.18'


class TestCommand(TestClass):
    user_options = []
    __dir__ = os.path.dirname(os.path.realpath(__file__))

    def initialize_options(self):
        super().initialize_options()
        sys.path.insert(0, os.path.join(self.__dir__, 'tests'))

    def run_tests(self):
        test_suite = unittest.TestLoader().discover('.', pattern='test_*.py')
        result = unittest.TextTestRunner(buffer=True).run(test_suite)
        sys.exit(not result.wasSuccessful())


cmdclass = {'test': TestCommand}

try:
    long_description = open("README.rst").read()
except IOError:
    long_description = ""

setup(
    name="perceval-gitee",
    version="0.1.0",
    description="Bundle of Perceval backends for Gitee",
    license="GPLV3",
    author="Willem Jiang",
    author_email="willem.jiang@gmail.com",

    long_description=long_description,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3'
    ],
    keywords="development repositories analytics for gitee",
    packages=[
        'perceval',
        'perceval.backends',
        'perceval.backends.gitee'
    ],
    namespace_packages=[
        'perceval',
        'perceval.backends'
    ],
    setup_requires=[
        'wheel',
        'pandoc'
    ],
    tests_require=[
        'httpretty>=0.9.6'
    ],
    install_requires=[
        'requests>=2.7.0',
        'grimoirelab-toolkit>=0.1.9',
        'perceval>=0.12.12'
    ],
    cmdclass=cmdclass,
    zip_safe=False)
