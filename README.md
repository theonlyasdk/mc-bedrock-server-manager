# Minecraft Bedrock Server Manager
MC Bedrock Server Manager is a simple and easy way to setup and manage your Minecraft Bedrock server, through the power of a GUI!

## Features
- A nice table view for editing `server.properties`
- Easy world backups management
- Start and manage server, view players list, all from a single view

## Screenshots

![Server Properties](docs/screenshots/server_properties.png)
![Management](docs/screenshots/server_management.png)
![Backups](docs/screenshots/backups.png)

## How to use
For now, no binaries are provided. A `build_installer.py` is provided for you to create your own binaries if you wish.
But it's quite easy to run it yourself.

1. Install a Python 3.11+ runtime (Tkinter is required, which should be installed on your system by default. If it isn't, install it using pip or with your system's package manager if you're on Linux and pip method doesn't work).
2. Clone/download this repository and extract it to a folder.
3. Run the app with `python3 src/mc_bedrock_server_manager.py` from the repository root.
4. In the Preferences tab, choose the folder where you've downloaded the Bedrock server folder and choose or create a backups folder.
5. Edit `server.properties` if needed, and click start server and enjoy!

## Notes
- Backup behaviour: Restoring a world renames the existing `worlds/<name>` directory to `Old_<world name>` (removing any previous `Old_<world name>`) before extracting the backup so the restored files reuse the original directory name.

## License
Licensed under the [MIT License](LICENSE)
