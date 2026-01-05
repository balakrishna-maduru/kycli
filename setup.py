from setuptools import setup, Extension
import sys
import os

# Try to import Cython, but don't fail if it's not available
try:
    from Cython.Build import cythonize
    USE_CYTHON = True
except ImportError:
    USE_CYTHON = False

include_dirs = []
library_dirs = []

# Detect Homebrew SQLite on macOS (especially Apple Silicon)
if sys.platform == "darwin":
    sqlite_prefix = "/opt/homebrew/opt/sqlite"
    if os.path.exists(sqlite_prefix):
        include_dirs.append(f"{sqlite_prefix}/include")
        library_dirs.append(f"{sqlite_prefix}/lib")

# Use the C file if available, otherwise use the .pyx file with Cython
ext_file = "kycli/kycore.c" if os.path.exists("kycli/kycore.c") else "kycli/kycore.pyx"

extensions = [
    Extension(
        "kycli.kycore",
        [ext_file],
        libraries=["sqlite3"],
        include_dirs=include_dirs,
        library_dirs=library_dirs,
    )
]

# Only use cythonize if we're building from .pyx and Cython is available
if ext_file.endswith(".pyx") and USE_CYTHON:
    extensions = cythonize(extensions)
elif ext_file.endswith(".pyx") and not USE_CYTHON:
    raise RuntimeError("Cython is required to build from .pyx files. Please install Cython or use a source distribution that includes the generated C files.")

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kycli",
    version="0.1.6",
    author="Balakrishna Maduru",
    author_email="balakrishnamaduru@gmail.com",
    description="**kycli** is a high-performance Python CLI toolkit built with Cython for speed.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=["kycli"],
    ext_modules=extensions,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Cython",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.9',
    install_requires=[
        "prompt-toolkit>=3.0.43",
        "rich>=13.7.0",
        "tomli>=2.0.1",
    ],
    entry_points={
        "console_scripts": [
            "kycli=kycli.cli:main",
            "kys=kycli.cli:main",
            "kyg=kycli.cli:main",
            "kyf=kycli.cli:main",
            "kyl=kycli.cli:main",
            "kyd=kycli.cli:main",
            "kyr=kycli.cli:main",
            "kyv=kycli.cli:main",
            "kye=kycli.cli:main",
            "kyi=kycli.cli:main",
            "kyc=kycli.cli:main",
            "kyh=kycli.cli:main",
            "kyshell=kycli.cli:main",
        ],
    },
)