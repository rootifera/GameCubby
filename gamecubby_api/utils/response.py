from fastapi.responses import JSONResponse


def success_response(message: str = "", data: dict | list | None = None):
    response = {"success": True}
    if message:
        response["message"] = message
    if data is not None:
        response["data"] = data
    return response


def error_response(message: str, status_code: int = 400):
    return JSONResponse(status_code=status_code, content={"success": False, "error": message})
