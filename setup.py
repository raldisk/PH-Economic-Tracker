"""
setup.py — installable package configuration.
Install: pip install -e .  (development)
         pip install .     (production)
"""
from setuptools import setup, find_packages

setup(
    name="ph-economic-tracker",
    version="0.1.0",
    description="Philippine PSA economic indicators + OFW remittance pipeline",
    python_requires=">=3.11",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "httpx>=0.27.0,<0.28",
        "pydantic>=2.7.0,<3",
        "pydantic-settings>=2.3.0,<3",
        "psycopg2-binary>=2.9.9,<3",
        "polars>=0.20.0,<1",
        "rich>=13.7.0,<14",
        "tenacity>=8.3.0,<9",
        "python-dotenv>=1.0.0,<2",
        "dbt-postgres>=1.8.0,<2",
        "typer>=0.12.0,<1",
        "streamlit>=1.35.0,<2",
        "plotly>=5.22.0,<6",
        "pandas>=2.2.0,<3",
    ],
    extras_require={
        "dev": [
            "pytest>=8.2.0,<9",
            "pytest-asyncio>=0.23.0,<1",
            "respx>=0.21.0,<1",
            "ruff>=0.4.0,<1",
            "mypy>=1.10.0,<2",
            "coverage[toml]>=7.5.0,<8",
            "pytest-cov>=5.0.0,<6",
        ]
    },
    entry_points={
        "console_scripts": [
            "ph-tracker=ph_economic.pipeline:app",
        ]
    },
)
