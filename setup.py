from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "kycli.kycore",
        ["kycli/kycore.pyx"],
    )
]

setup(
    name="kycli",
    version="0.1.3",
    author="Balakrishna Maduru",
    author_email="balakrishnamaduru@gmail.com",
    description="**kycli** is a high-performance Python CLI toolkit built with Cython for speed.",
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
            "kyh=kycli.cli:main",
        ],
    },
)