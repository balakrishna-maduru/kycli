# setup.py
from setuptools import setup
from Cython.Build import cythonize

setup(
    name="kycli",
    ext_modules=cythonize("kycli/kycore.pyx"),
    packages=["kycli"]
)