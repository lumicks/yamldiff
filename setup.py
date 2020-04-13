import os
import sys
from setuptools import setup, find_packages
from setuptools.command.egg_info import manifest_maker

if sys.version_info[:2] < (3, 6):
    print("Python >= 3.6 is required.")
    sys.exit(-1)

requires = ['ruamel.yaml>=0.15.66', 'colorama>=0.3.9']

def about(package):
    ret = {}
    filename = os.path.join(os.path.dirname(__file__), package, '__about__.py')
    with open(filename, 'rb') as file:
        exec(compile(file.read(), filename, 'exec'), ret)
    return ret


def read(filename):
    if not os.path.exists(filename):
        return ''

    with open(filename) as f:
        return f.read()


info = about('yamldiff')
manifest_maker.template = 'setup.manifest'

setup(
    name=info['__title__'],
    version=info['__version__'],
    description=info['__summary__'],
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    url=info['__url__'],
    license=info['__license__'],

    author=info['__author__'],
    author_email=info['__email__'],

    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
    ],

    entry_points={
        'console_scripts': [
            'yamldiff=yamldiff.yamldiff:main',
        ],
    },

    python_requires='>=3',
    install_requires=requires,
    packages=find_packages(exclude=['test*']),
    include_package_data=True
)
