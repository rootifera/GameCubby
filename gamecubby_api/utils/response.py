from fastapi.responses import JSONResponse


def success_response(message: str = "", data: dict = None):
    resp = {"success": True}
    if message:
        resp["message"] = message
    if data is not None:
        resp["data"] = data
    return resp


def error_response(message: str, status_code: int = 400):
    return JSONResponse(status_code=status_code, content={"success": False, "error": message})
