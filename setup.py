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

# Determine if we use Cython or pre-generated C files
USE_CYTHON_SOURCE = os.path.exists("kycli/core/storage.pyx")

modules = [
    "kycli.core.engine",
    "kycli.core.security",
    "kycli.core.query",
    "kycli.core.audit",
    "kycli.core.storage",
]

extensions = []
for mod in modules:
    rel_path = mod.replace(".", "/")
    pyx_path = f"{rel_path}.pyx"
    c_path = f"{rel_path}.c"
    
    source = pyx_path if USE_CYTHON_SOURCE and USE_CYTHON else c_path
    if os.path.exists(source):
        extensions.append(
            Extension(
                mod,
                [source],
                libraries=["sqlite3"],
                include_dirs=include_dirs,
                library_dirs=library_dirs,
            )
        )

if USE_CYTHON and USE_CYTHON_SOURCE:
    extensions = cythonize(extensions, language_level="3")
elif USE_CYTHON_SOURCE and not USE_CYTHON:
    raise RuntimeError("Cython is required to build from source.")

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kycli",
    version="0.2.3",
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
        "cryptography>=42.0.0",
    ],
    entry_points={
        "console_scripts": [
            "kycli=kycli.cli:main",
            "kys=kycli.cli:main",
            "kyg=kycli.cli:main",
            "kyl=kycli.cli:main",
            "kyd=kycli.cli:main",
            "kyr=kycli.cli:main",
            "kyv=kycli.cli:main",
            "kye=kycli.cli:main",
            "kyi=kycli.cli:main",
            "kyc=kycli.cli:main",
            "kyh=kycli.cli:main",
            "kyshell=kycli.cli:main",
            "kyuse=kycli.cli:main",
            "kyws=kycli.cli:main",
            "kymv=kycli.cli:main",
            "kyinit=kycli.cli:main",
        ],
    },
)