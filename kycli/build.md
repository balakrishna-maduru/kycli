
# Building the Cython extension for kycli
# Ensure you have Cython installed
bash````
pip install cython
```

# Navigate to the kycli directory
bash```
cd kycli
python setup.py build_ext --inplace
```

# Install the package in editable mode
bash```
pip install -e .
```
# This will compile the Cython files and install the package
# in editable mode, allowing you to make changes to the source code
# and have them reflected immediately without needing to reinstall.
```
# After running the above commands, you should be able to use kycli
# with the Cython optimizations.
# If you encounter any issues, ensure that you have the necessary
# build tools installed for your platform (e.g., `build-essential` on Debian/Ubuntu).