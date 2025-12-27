#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setup script for Stow-Python - Python reimplementation of GNU Stow.

Works with Python 2.7+ and Python 3.0+.
"""

from setuptools import setup
import os

# Read version from the package
here = os.path.abspath(os.path.dirname(__file__))
version = '2.4.1'

# Try to read version from source
try:
    with open(os.path.join(here, 'bin', 'stow')) as f:
        for line in f:
            if line.startswith('VERSION'):
                version = line.split('=')[1].strip().strip("'\"")
                break
except Exception:
    pass

setup(
    name='stow-python',
    version=version,
    description='Stow-Python - Python reimplementation of the GNU Stow symlink farm manager',
    long_description=open('README.md').read() if os.path.exists('README.md') else '',
    long_description_content_type='text/markdown',
    author='Istvan Sarandi',
    author_email='istvan.sarandi@gmail.com',
    url='https://github.com/isarandi/stow-python',
    license='GPL-3.0-or-later',
    scripts=['bin/stow', 'bin/chkstow'],
    python_requires='>=2.7',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: POSIX',
        'Operating System :: Unix',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.0',
        'Programming Language :: Python :: 3.1',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Systems Administration',
    ],
    keywords='stow symlink dotfiles package-manager',
)
