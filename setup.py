from setuptools import setup, Extension
from Cython.Build import cythonize

import os

# Detect Homebrew SQLite if on Apple Silicon Mac
sqlite_prefix = "/opt/homebrew/opt/sqlite"
include_dirs = []
library_dirs = []
if os.path.exists(sqlite_prefix):
    include_dirs.append(f"{sqlite_prefix}/include")
    library_dirs.append(f"{sqlite_prefix}/lib")

extensions = [
    Extension(
        "kycli.kycore",
        ["kycli/kycore.pyx"],
        libraries=["sqlite3"],
        include_dirs=include_dirs,
        library_dirs=library_dirs,
    )
]

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kycli",
    version="0.1.7",
    author="Balakrishna Maduru",
    author_email="balakrishnamaduru@gmail.com",
    description="**kycli** is a high-performance Python CLI toolkit built with Cython for speed.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=["kycli"],
    ext_modules=cythonize(extensions),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Cython",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.9',
    entry_points={
        "console_scripts": [
            "kys=kycli.cli:main",
            "kyg=kycli.cli:main",
            "kyl=kycli.cli:main",
            "kyd=kycli.cli:main",
            "kyr=kycli.cli:main",
            "kyv=kycli.cli:main",
            "kye=kycli.cli:main",
            "kyi=kycli.cli:main",
            "kyh=kycli.cli:main",
        ],
    },
)