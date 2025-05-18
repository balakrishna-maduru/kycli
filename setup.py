from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "kycli.kycore",
        ["kycli/kycore.pyx"],
        # add extra compile/link args if needed
    )
]

setup(
    name="kycli",
    version="0.1.0",
    author="Your Name",
    author_email="you@example.com",
    description="Your KV store CLI tool",
    packages=["kycli"],
    ext_modules=cythonize(extensions),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Cython",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    entry_points={
        "console_scripts": [
            "kys=kycli.cli:main",  # adjust if your cli.py has a main() entry
            "kyg=kycli.cli:main",
            "kyl=kycli.cli:main",
            "kyd=kycli.cli:main",
            "kyh=kycli.cli:main",
        ],
    },
)