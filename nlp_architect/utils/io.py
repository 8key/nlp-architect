# ******************************************************************************
# Copyright 2017-2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ******************************************************************************
import argparse
import io
import os
import posixpath
import re
import zipfile

import requests
from tqdm import tqdm


def download_unlicensed_file(url, sourcefile, destfile, totalsz=None):
    """
    Download the file specified by the given URL.

    Args:
        url (str): url to download from
        sourcefile (str): file to download from url
        destfile (str): save path
        totalsz (:obj:`int`, optional): total size of file
    """
    req = requests.get(posixpath.join(url, sourcefile),
                       stream=True)

    chunksz = 1024 ** 2
    if totalsz is None:
        if "Content-length" in req.headers:
            totalsz = int(req.headers["Content-length"])
            nchunks = totalsz // chunksz
        else:
            print("Unable to determine total file size.")
            nchunks = None
    else:
        nchunks = totalsz // chunksz

    print("Downloading file to: {}".format(destfile))
    with open(destfile, 'wb') as f:
        for data in tqdm(req.iter_content(chunksz), total=nchunks, unit="MB"):
            f.write(data)
    print("Download Complete")


def unzip_file(filepath, outpath='.'):
    """
    Unzip a file to the same location of filepath

    Args:
        filepath (str): path to file
        outpath (str): path to extract to
    """
    z = zipfile.ZipFile(filepath, 'r')
    z.extractall(outpath)
    z.close()


def walk_directory(directory):
    """Iterates a directory's text files and their contents."""
    for dir_path, _, filenames in os.walk(directory):
        for filename in filenames:
            file_path = os.path.join(dir_path, filename)
            if os.path.isfile(file_path) and not filename.startswith('.'):
                with io.open(file_path, 'r', encoding='utf-8') as file:
                    print('Reading ' + filename)
                    doc_text = file.read()
                    yield filename, doc_text


def validate(*args):
    """
    Validate all arguments are of correct type and in correct range.
    Args:
        *args (tuple of tuples): Each tuple represents an argument validation like so:
        Option 1 - With range check:
            (arg, class, min_val, max_val)
        Option 2 - Without range check:
            (arg, class)
        If class is a tuple of type objects check if arg is an instance of any of the types.
        To allow a None valued argument, include type(None) in class.
        To disable lower or upper bound check, set min_val or max_val to None, respectively.
        If arg has the len attribute (such as string), range checks are performed on its length.
    """
    for arg in args:
        arg_val = arg[0]
        arg_type = (arg[1],) if isinstance(arg[1], type) else arg[1]
        if not isinstance(arg_val, arg_type):
            raise TypeError('Expected type {}'.format(' or '.join([t.__name__ for t in arg_type])))
        if arg_val is not None and len(arg) >= 4:
            name = 'of ' + arg[4] if len(arg) == 5 else ''
            arg_min = arg[2]
            arg_max = arg[3]
            if hasattr(arg_val, '__len__'):
                val = 'Length'
                num = len(arg_val)
            else:
                val = 'Value'
                num = arg_val
            if arg_min is not None and num < arg_min:
                raise ValueError('{} {} must be greater or equal to {}'.format(val, name, arg_min))
            if arg_max is not None and num >= arg_max:
                raise ValueError('{} {} must be less than {}'.format(val, name, arg_max))


def validate_existing_filepath(arg):
    """Validates an input argument is a path string to an existing file."""
    validate((arg, str, 0, 255))
    if not os.path.isfile(arg):
        raise ValueError("{0} does not exist.".format(arg))
    return arg


def validate_existing_directory(arg):
    """Validates an input argument is a path string to an existing directory."""
    arg = os.path.abspath(arg)
    validate((arg, str, 0, 255))
    if not os.path.isdir(arg):
        raise ValueError("{0} does not exist".format(arg))
    return arg


def validate_parent_exists(arg):
    """Validates an input argument is a path string, and its parent directory exists."""
    arg = os.path.abspath(arg)
    dir_arg = os.path.dirname(os.path.abspath(arg))
    if validate_existing_directory(dir_arg):
        return arg
    return None


def sanitize_path(path):
    s_path = os.path.normpath('/' + path).lstrip('/')
    assert len(s_path) < 255
    return s_path


def check(validator):
    class CustomAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            validator(values)
            setattr(namespace, self.dest, values)

    return CustomAction


def check_size(min_size=None, max_size=None):
    class CustomAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            validate((values, self.type, min_size, max_size, self.dest))
            setattr(namespace, self.dest, values)

    return CustomAction


def validate_proxy_path(arg):
    """Validates an input argument is a valid proxy path or None"""
    proxy_validation_regex = re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    if arg is not None and re.match(proxy_validation_regex, arg) is None:
        raise ValueError("{0} is not a valid proxy path".format(arg))
    return arg
