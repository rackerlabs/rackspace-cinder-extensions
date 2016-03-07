#!/usr/bin/env python

# Copyright 2013-2016 Rackspace US, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from setuptools import setup, find_packages

version = '0.4'

setup(
    name='rackspace_cinder_extensions',
    version=version,
    author='Cory Stone',
    author_email='cory.stone@gmail.com',
    maintainer='Cory Wright',
    maintainer_email='corywright@gmail.com',
    description='Rackspace Cinder Extensions',
    license='Apache License, Version 2.0',
    packages=find_packages(exclude=['test']),
    url='https://github.com/rackerlabs/rackspace_cinder_extensions',
    install_requires=['python-lunrclient>=1.1.0'],
    data_files=[
        ('share/doc/python-rackspace-cinder-extensions',
         ['CHANGES', 'CONTRIBUTORS', 'LICENSE', 'README.md']),
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        'Environment :: OpenStack',
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        'Intended Audience :: System Administrators',
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
    ]
)
