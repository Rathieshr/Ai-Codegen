"""Setuptools compatibility shim for older pip editable installs."""

from setuptools import find_packages, setup


setup(
    name="ai-gen",
    version="0.1.0",
    description="Inject business logic-aware context before Codex runs.",
    packages=find_packages("."),
    package_data={"logic_store": ["*.json"]},
    install_requires=["fastapi>=0.100", "uvicorn[standard]>=0.22"],
    python_requires=">=3.9",
    entry_points={"console_scripts": ["ai-gen=cli.app:main"]},
)
