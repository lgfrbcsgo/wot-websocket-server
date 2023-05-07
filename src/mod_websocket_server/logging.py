try:
    from debug_utils import LOG_NOTE
except ImportError:
    def LOG_NOTE(msg):
        print msg