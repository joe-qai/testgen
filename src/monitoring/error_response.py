class ErrorResponse:
    @staticmethod
    def create(message, code, request_id, details=None):
        response = {
            "error": message,
            "code": code,
            "request_id": request_id
        }
        if details:
            response["details"] = details
        return response

