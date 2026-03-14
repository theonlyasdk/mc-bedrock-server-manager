import tkinter as tk
from tkinter import ttk

from constants import APP_NAME


def prompt_string(parent, label_text, initial_value=""):
    dialog = tk.Toplevel(parent)
    dialog.title(APP_NAME)
    dialog.transient(parent)
    dialog.withdraw()

    frame = ttk.Frame(dialog, padding=12)
    frame.pack(fill="both", expand=True)

    label = ttk.Label(frame, text=label_text, anchor="w", justify="left")
    label.pack(fill="x", anchor="w")

    entry = ttk.Entry(frame)
    entry.pack(fill="x", pady=(8, 0))
    entry.insert(0, initial_value)
    entry.focus_set()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(12, 0))
    result = {"value": None}

    def on_ok():
        result["value"] = entry.get()
        dialog.destroy()

    def on_cancel():
        result["value"] = None
        dialog.destroy()

    ttk.Button(buttons, text="OK", command=on_ok).pack(side="right", padx=4)
    ttk.Button(buttons, text="Cancel", command=on_cancel).pack(side="right")

    dialog.update_idletasks()
    width = max(380, dialog.winfo_reqwidth())
    height = dialog.winfo_reqheight() + 40
    x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (width // 2)
    y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (height // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")

    dialog.bind("<Return>", lambda _e: on_ok())
    dialog.bind("<Escape>", lambda _e: on_cancel())

    dialog.deiconify()
    dialog.wait_visibility()
    dialog.grab_set()

    parent.wait_window(dialog)
    return result["value"]


def confirm_dialog(parent, message, *, min_width=520, wraplength=520, extra_width=200):
    dialog = tk.Toplevel(parent)
    dialog.title(APP_NAME)
    dialog.transient(parent)
    dialog.withdraw()

    frame = ttk.Frame(dialog, padding=12)
    frame.pack(fill="both", expand=True)

    label = ttk.Label(frame, text=message, anchor="w", justify="left", wraplength=wraplength)
    label.pack(fill="x", anchor="w")

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(16, 0))
    result = {"value": False}

    def on_yes():
        result["value"] = True
        dialog.destroy()

    def on_no():
        result["value"] = False
        dialog.destroy()

    ttk.Button(buttons, text="Yes", command=on_yes).pack(side="right", padx=4)
    ttk.Button(buttons, text="No", command=on_no).pack(side="right")

    dialog.update_idletasks()
    width = max(min_width, dialog.winfo_reqwidth()) + extra_width
    height = dialog.winfo_reqheight() + 40
    x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (width // 2)
    y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (height // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")

    dialog.bind("<Return>", lambda _e: on_yes())
    dialog.bind("<Escape>", lambda _e: on_no())

    dialog.deiconify()
    dialog.wait_visibility()
    dialog.grab_set()

    parent.wait_window(dialog)
    return result["value"]


def show_validation_dialog(parent, errors):
    dialog = tk.Toplevel(parent)
    dialog.title(APP_NAME)
    dialog.transient(parent)
    dialog.withdraw()

    frame = ttk.Frame(dialog, padding=12)
    frame.pack(fill="both", expand=True)

    title = ttk.Label(frame, text="Server Validation Results", anchor="w", justify="left")
    title.pack(fill="x", anchor="w")

    listbox = tk.Listbox(frame, height=10)
    listbox.pack(fill="both", expand=True, pady=(8, 0))
    if errors:
        for key, reason in errors:
            listbox.insert(tk.END, f"{key}: {reason}")
    else:
        listbox.insert(tk.END, "No issues found.")

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(12, 0))
    ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side="right")

    dialog.update_idletasks()
    width = max(520, dialog.winfo_reqwidth())
    height = max(320, dialog.winfo_reqheight())
    x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (width // 2)
    y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (height // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")

    dialog.deiconify()
    dialog.wait_visibility()
    dialog.grab_set()

    parent.wait_window(dialog)
