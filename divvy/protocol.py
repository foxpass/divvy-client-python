from collections import namedtuple
import re
from types import StringTypes

from divvy.exceptions import InputError, ParseError, ServerError


Response = namedtuple(
    "Response",
    [
        "is_allowed",  # True or False, indicating whether quota was available
        "current_credit",  # number of credit(s) available after this command
        "next_reset_seconds"  # time, in seconds, until credit next resets
    ]
)


class Translator(object):
    STRING_REGEXP = re.compile('^[^"=\\s]+$')
    RESPONSE_REGEXP = re.compile('^OK (true|false) (\\d+) (\\d+)$')
    ERROR_REGEXP = re.compile('^ERR (unknown|unknown-command) "?([^"]+)"?$')

    def __init__(self, encoding='utf-8'):
        self.encoding = encoding

    def build_hit(self, **kwargs):
        """Builds a HIT command with the given arguments. Returns bytes."""
        cmd = b"HIT"
        for k in sorted(kwargs.keys()):
            v = kwargs[k]
            if not isinstance(v, StringTypes):
                v = str(v)
            if not self.STRING_REGEXP.match(k):
                raise InputError("Invalid Divvy key {}".format(k))
            if not self.STRING_REGEXP.match(v):
                raise InputError("Invalid Divvy value {}".format(v))
            cmd += b" \"" + k.encode(self.encoding) + b"\"=\"" + \
                v.encode(self.encoding) + b"\""
        cmd += b"\n"
        return cmd

    def parse_reply(self, reply_bytes):
        """Builds a Resopnse object based on the server's reply."""
        reply = reply_bytes.decode(self.encoding)
        response = self.RESPONSE_REGEXP.match(reply)
        if not response:
            error = self.ERROR_REGEXP.match(reply)
            if error:
                raise ServerError(error_code=error.group(1),
                                  message=error.group(2))
            else:
                raise ParseError("Unable to parse reply: {}".format(reply))
        return Response(is_allowed=response.group(1) == "true",
                        current_credit=int(response.group(2)),
                        next_reset_seconds=int(response.group(3)))
