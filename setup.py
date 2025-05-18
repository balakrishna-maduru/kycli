# setup.py
from setuptools import setup
from Cython.Build import cythonize
from setuptools.extension import Extension

extensions = [
    Extension(
        "kycli.kycore",
        ["kycli/kycore.pyx"],
    )
]

setup(
    name="kycli",
    ext_modules=cythonize(extensions),
    zip_safe=False,
)