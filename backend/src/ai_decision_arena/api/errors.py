"""The API's own exception. main.py turns it into {"error": {"code", "message"}} with the given status."""


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code, self.code, self.message = status_code, code, message
