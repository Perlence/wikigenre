from setuptools import setup

README = open('README.md').read()

setup(
    name='wikigenre',
    version='1.0',
    author='Sviatoslav Abakumov',
    author_email='dust.harvesting@gmail.com',
    description='A foobar2000 companion designed to fetch genres',
    long_description=README,
    url='https://github.com/Perlence/wikigenre',
    download_url='https://github.com/Perlence/wikigenre/archive/master.zip',
    py_modules=['wikigenre'],
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'wikigenre = wikigenre:main',
        ],
    },
    install_requires=[
        'gevent',
        'lxml',
        'mutagen',
        'requests',
        'wikiapi',
    ],
    classifiers=[
        'Development Status :: 3 - Stable',
        'Environment :: Console',
        'License :: OSI Approved :: BSD License',
        'Operating System :: Windows',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Topic :: Multimedia :: Sound/Audio',
    ]
)
