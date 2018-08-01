from setuptools import find_packages, setup


setup(
    name='divvy-client-python',
    version='2.0.0',
    description="Python client to the Divvy quota service",
    url='https://github.com/foxpass/divvy-client-python/',
    author='Ryan Park',
    author_email='ryan@foxpass.com',
    packages=find_packages(exclude=["tests"]),
    zip_safe=False,
    platforms='any',
    classifiers=[
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    install_requires=[],
    tests_require=[]
)
