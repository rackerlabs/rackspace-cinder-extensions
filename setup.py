import setuptools


setuptools.setup(
    name='rackspace_cinder_extensions',
    version='0.1',
    author='Rackspace',
    author_email='cory.stone@gmail.com',
    description='Rackspace Cinder Extensions',
    license='Apache License, Version 2.0',
    packages=['rackspace_cinder_extensions'],
    url='https://github.com/rackerlabs/rackspace-cinder-extensions',
    install_requires=['cinder'],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
    ]
)
