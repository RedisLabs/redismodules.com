from setuptools import setup

setup(
    name='rmhub',
    version='0.1',
    description='Redis Modules Hub',
    author='Redis Labs',
    author_email='oss@redislabs.com',
    license='BSD3',
    packages=['rmhub'],
    include_package_data=True,
    setup_requires=['nose>=1.0'],
    install_requires=[
        'python-dotenv',
        'redis',
        'redisearch',
        'rejson',
        'rq',
        'rq-scheduler',
        'PyGithub',
    ],
    extras_require={
        'web': [
            'Flask',
            'Flask-Bootstrap',
            'Flask-Cache',
            'markdown',
            'validators',
        ],
    },
    test_suite='nose.collector',
    tests_require=['nose'],
)