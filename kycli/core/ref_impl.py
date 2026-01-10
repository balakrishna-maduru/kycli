def import_data(self, str file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with open(file_path, "r") as f:
        if file_path.endswith(".json"):
            data = json.load(f)
            if isinstance(data, dict):
                self.save_many(list(data.items()))
            elif isinstance(data, list):
                # Assume list of [key, value] pairs
                self.save_many(data)
            else:
                raise ValueError("JSON must be a dictionary or list of pairs.")
        
        elif file_path.endswith(".csv"):
            import csv
            reader = csv.reader(f)
            items = []
            for row in reader:
                if len(row) >= 2:
                    items.append((row[0], row[1]))
            self.save_many(items)
        else:
            raise ValueError("Unsupported format. Use .json or .csv")

def export_data(self, str file_path, str fmt="csv"):
    data = {}
    for k in self:
        data[k] = self.getkey(k)
        
    if fmt == "json":
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
    elif fmt == "csv":
        import csv
        with open(file_path, "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Key", "Value"])
            for k, v in data.items():
                writer.writerow([k, json.dumps(v) if isinstance(v, (dict, list)) else v])
    else:
        raise ValueError("Unsupported format. Use 'json' or 'csv'")
