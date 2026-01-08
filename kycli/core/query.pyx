# cython: language_level=3
import re

cdef class QueryEngine:
    cpdef navigate(self, data, str path):
        if not path:
            return data
        tokens = re.findall(r'\.?([^.\[\]\s]+)|\[([^\]]+)\]', path)
        current = data
        for attr, idx in tokens:
            if attr:
                if isinstance(current, dict):
                    if attr in current:
                        current = current[attr]
                    else:
                        return f"KeyError: '{attr}' not found"
                else:
                    return f"TypeError: Cannot get '{attr}' from non-dict"
            elif idx:
                if isinstance(current, list):
                    if ":" in idx:
                        try:
                            parts = idx.split(':')
                            start = int(parts[0]) if parts[0] else None
                            end = int(parts[1]) if parts[1] else None
                            current = current[slice(start, end)]
                        except:
                            return f"SliceError: '{idx}'"
                    else:
                        try:
                            i = int(idx)
                            current = current[i]
                        except (ValueError, IndexError):
                            return f"IndexError: '{idx}'"
                else:
                    return f"TypeError: Cannot index non-list with '{idx}'"
        return current

    cpdef patch_value(self, data, str path, value):
        if not path:
            return value
        tokens = re.findall(r'\.?([^.\[\]\s]+)|\[([^\]]+)\]', path)
        if not tokens:
            return value
        if data is None or not isinstance(data, (dict, list)):
            data = {} if tokens[0][0] else []
        current = data
        for i in range(len(tokens) - 1):
            attr, idx = tokens[i]
            next_attr, next_idx = tokens[i+1]
            if attr:
                if attr not in current or not isinstance(current[attr], (dict, list)):
                    current[attr] = {} if next_attr else []
                current = current[attr]
            elif idx:
                i_idx = int(idx)
                while len(current) <= i_idx:
                    current.append(None)
                if current[i_idx] is None or not isinstance(current[i_idx], (dict, list)):
                    current[i_idx] = {} if next_attr else []
                current = current[i_idx]
        attr, idx = tokens[-1]
        if attr:
            current[attr] = value
        elif idx:
            i_idx = int(idx)
            while len(current) <= i_idx:
                current.append(None)
            current[i_idx] = value
        return data
