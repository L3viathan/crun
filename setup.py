from setuptools import setup, find_packages

setup(
    name="crun",
    version="2.11.1",
    install_requires=[
        "click",
        "toml",
    ],
    author="L3viathan",
    author_email="git@l3vi.de",
    description="Run pipelines according to configuration files",
    url="https://github.com/L3viathan/crun",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Intended Audience :: Developers",
    ],
    entry_points={
        "console_scripts": ["crun=crun.runner:cli"],
    },
)
