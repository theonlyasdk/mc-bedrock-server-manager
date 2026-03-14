import os
from tkinter import ttk


def apply_theme():
    style = ttk.Style()
    available = set(style.theme_names())
    if os.name == "nt" and "vista" in available:
        style.theme_use("vista")
        return "vista"
    for name in ("yaru", "clam", "xpnative", "aqua", "alt", "default", "classic"):
        if name in available:
            style.theme_use(name)
            return name
    return style.theme_use()
