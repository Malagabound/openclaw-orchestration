"""OpenClawd Agent Dispatch System - Package Setup.

Provides the 'openclawd' CLI entry point via console_scripts.
"""

from setuptools import setup

setup(
    name="openclawd",
    version="0.1.0",
    packages=["agent-dispatch", "agent-dispatch.health"],
    entry_points={
        "console_scripts": [
            "openclawd=agent-dispatch.cli:main",
        ],
    },
    python_requires=">=3.9",
    install_requires=[
        "PyYAML",
    ],
)
