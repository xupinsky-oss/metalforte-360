"""Credenciais portáveis para execução local e em nuvem."""

import os

TARGET = "Metalforte360/GoodData"


def _environment_credential():
    login = os.getenv("TOTVS_LOGIN", "").strip()
    password = os.getenv("TOTVS_PASSWORD", "")
    if login and password:
        return {"login": login, "password": password}
    return None


def _windows_api():
    if os.name != "nt":
        raise RuntimeError(
            "Credenciais não configuradas. Defina TOTVS_LOGIN e TOTVS_PASSWORD."
        )
    import ctypes
    from ctypes import wintypes

    class CredentialW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
        ]

    api = ctypes.windll.advapi32
    api.CredWriteW.argtypes = [ctypes.POINTER(CredentialW), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CredentialW))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredDeleteW.restype = wintypes.BOOL
    return ctypes, api, CredentialW


def save_credential(path, login, password):
    del path
    ctypes, api, credential_type = _windows_api()
    encoded = password.encode("utf-16-le")
    blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    cred = credential_type(Type=1, TargetName=TARGET,
        Comment="Atualização automática Metalforte 360",
        CredentialBlobSize=len(encoded), CredentialBlob=blob,
        Persist=2, UserName=login)
    if not api.CredWriteW(ctypes.byref(cred), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def load_credential(path=None):
    del path
    environment = _environment_credential()
    if environment:
        return environment
    ctypes, api, credential_type = _windows_api()
    pointer = ctypes.POINTER(credential_type)()
    if not api.CredReadW(TARGET, 1, 0, ctypes.byref(pointer)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        cred = pointer.contents
        raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        return {"login": cred.UserName, "password": raw.decode("utf-16-le")}
    finally:
        api.CredFree(pointer)


def delete_credential():
    ctypes, api, _ = _windows_api()
    if not api.CredDeleteW(TARGET, 1, 0):
        error = ctypes.get_last_error()
        if error != 1168:
            raise ctypes.WinError(error)
