# kycore.pyx
from libc.string cimport strdup
import os
import pickle

cdef class Kycore:
    cdef dict _store
    cdef str _data_path

    def __cinit__(self):
        self._store = {}
        self._data_path = os.path.expanduser("~/.kycli/kydata.pkl")
        os.makedirs(os.path.dirname(self._data_path), exist_ok=True)
        self._load()

    @property
    def data_path(self):
        # Expose _data_path to Python as a property
        return self._data_path

    def save(self, str key, str value):
        self._store[key.lower()] = value
        self._persist()

    def getkey(self, str key):
        return self._store.get(key.lower(), "Key not found")

    def delete(self, str key):
        if key.lower() in self._store:
            del self._store[key.lower()]
            self._persist()
            return "Deleted"
        return "Key not found"

    def listkeys(self):
        return list(self._store.keys())

    @property
    def store(self):
        return self._store

    def load_store(self, dict store_data):
        self._store = store_data

    cdef void _persist(self):
        with open(self._data_path, "wb") as f:
            pickle.dump(self._store, f)

    cdef void _load(self):
        try:
            with open(self._data_path, "rb") as f:
                self._store = pickle.load(f)
        except FileNotFoundError:
            self._store = {}