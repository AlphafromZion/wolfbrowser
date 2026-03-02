from setuptools import setup, find_packages

setup(
    name="wolfbrowser",
    version="0.1.0",
    description="Stealth browser toolkit — CDP-based, anti-detection, human-like interaction",
    author="Alpha",
    author_email="alpha@ziondelta.com",
    url="https://github.com/AlphafromZion/wolfbrowser",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "websockets>=12.0",
        "httpx>=0.25.0",
    ],
    entry_points={
        "console_scripts": [
            "wolfbrowser=wolfbrowser.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Internet :: WWW/HTTP :: Browsers",
    ],
)
