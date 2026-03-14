# Minecraft Bedrock Server Manager

## Features
- Inspect and edit every entry in `server.properties` through a table view that saves changes back to disk automatically.
- Manage backups with listing, creation, restore, rename, delete, and quick-folder access buttons.
- Easy server control: start/stop, live console I/O, player counts, and whitelist/ops/players management pages.

## How to use
1. Install a Python 3.11+ runtime (Tkinter is required, so include the OS-provided GUI packages on Linux).
2. Run the manager with `python -m src.mc_bedrock_server_manager` from the repository root.
3. In the Preferences tab, point to your Bedrock server folder and choose or create a backups folder.
4. Use the other tabs to edit properties, manage backups, and operate the server without touching the command line.

## Notes
- Backup behaviour: restoring a world renames the existing `worlds/<name>` directory to `Old_<world name>` (removing any previous `Old_<world name>`) before extracting the backup so the restored files reuse the original directory name.

## License
[MIT License](LICENSE)
