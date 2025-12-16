from bot import Bot
import logging

try:
    import uvloop
    uvloop.install()
except ImportError:
    pass

Bot().run()
