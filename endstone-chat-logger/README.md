# Endstone Chat Logger

This plugin logs player chat to the server console in a `[CHAT] <player>: <message>` format so the Web Manager can ingest it.

## Install
From the repository root:

```bash
cd endstone-chat-logger
pip install -e .
```

Then restart your Endstone server. The plugin should log a startup line and then `[CHAT]` lines for chat messages.

## Notes
- If your Endstone build uses a different API version, update `api_version` in `src/endstone_chat_logger/plugin.py`.
- This plugin targets Endstone (not vanilla BDS). It will not work without Endstone.
