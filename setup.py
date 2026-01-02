from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "kycli.kycore",
        ["kycli/kycore.pyx"],
    )
]

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="kycli",
    version="0.1.1",
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
            "kyv=kycli.cli:main",
            "kye=kycli.cli:main",
            "kyi=kycli.cli:main",
            "kyh=kycli.cli:main",
        ],
    },
)