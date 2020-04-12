

# conf = {
#     'disabled': bool(env('TELEGRAM_DISABLED', False)),
#     'bot': env("TELEGRAM_TOKEN", ""),
#     'chat': env("TELEGRAM_CHAT", ""),
# }
import urllib.parse

import requests

class TelegramError(Exception):
    pass

class Telegram:
    # setup telegram

    def __init__(self, conf):
        self.prefix = \
            "https://api.telegram.org/bot{token}/{{method}}?chat_id={chatID}".format(
                token=conf["bot"],
                chatID=conf["chat"],
            )
        self.msgFormat = self.prefix.format(method="sendMessage") + "&parse_mode=Markdown&text={}"
        self.enabled = not conf["disabled"]
        self.online = False
        if not self.enabled:
            return
        self.checkConn()

    def checkConn(self):
        try:
            # check that telegram is working
            resp = requests.get(self.prefix.format(method="getMyCommands"))
            respJson = resp.json()
            if not "ok" in respJson or not respJson["ok"]:
                raise Exception(repr(respJson))
        except:
            self.online = False
            raise
        else:
            self.online = True

    def sendMessage(self, msg):
        if not self.enabled:
            return
        if not self.online:
            self.checkConn()
        try:
            resp = requests.get(self.msgFormat.format(urllib.parse.quote(msg)))
            if not resp.json()["ok"]:
                raise Exception(repr(resp.json()))
        except Exception as err:
            raise TelegramError("telegram api call error: %s" % err)
