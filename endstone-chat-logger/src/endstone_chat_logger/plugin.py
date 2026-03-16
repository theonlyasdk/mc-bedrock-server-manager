from endstone.event import EventPriority, PlayerChatEvent, event_handler
from endstone.plugin import Plugin


class ChatLoggerPlugin(Plugin):
    prefix = "ChatLogger"
    api_version = "0.10"
    load = "POSTWORLD"

    def on_enable(self) -> None:
        self.logger.info("Chat Logger enabled.")
        self.register_events(self)

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_player_chat(self, event: PlayerChatEvent) -> None:
        player_name = getattr(event.player, "name", "Unknown")
        message = event.message
        if not message:
            return
        self.logger.info(f"[CHAT] {player_name}: {message}")
