class DivvyError(Exception):
    pass


class ConnectionError(DivvyError):
    pass


class InputError(DivvyError):
    pass


class ParseError(DivvyError):
    pass


class ServerError(DivvyError):
    def __init__(self, error_code, message):
        self.error_code = error_code
        self.message = message
        super(ServerError, self).__init__(message)


class TimeoutError(DivvyError):
    pass
