import os


class PropertiesFile:
    def __init__(self, path):
        self.path = path
        self.lines = []
        self.data = {}

    def load(self):
        self.lines = []
        self.data = {}
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                self.lines.append(line.rstrip("\n"))
        for line in self.lines:
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            self.data[key.strip()] = value

    def set_value(self, key, value):
        self.data[key] = value
        updated = False
        for i, line in enumerate(self.lines):
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            k, _ = line.split("=", 1)
            if k.strip() == key:
                comment = ""
                hash_index = line.find("#")
                if hash_index > 0 and line[hash_index - 1].isspace():
                    comment = line[hash_index:]
                self.lines[i] = f"{k}={value}{comment}"
                updated = True
                break
        if not updated:
            self.lines.append(f"{key}={value}")

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")
