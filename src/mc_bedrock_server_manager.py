from app import App


def main():
    app = App()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        try:
            if app.winfo_exists():
                app._on_close()
        except Exception:
            try:
                app.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    main()
