"""OS clipboard bridge for terminal TUI (pyperclip + Windows ctypes fallback)."""

from __future__ import annotations

import sys
from typing import Final

CF_UNICODETEXT: Final[int] = 13
CF_HDROP: Final[int] = 15
GMEM_MOVEABLE: Final[int] = 0x0002


def _win32_clipboard_read() -> str | None:
    import ctypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _win32_clipboard_write(text: str) -> bool:
    import ctypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        encoded = (text + "\0").encode("utf-16-le")
        size = len(encoded)
        hglobal = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not hglobal:
            return False
        ptr = kernel32.GlobalLock(hglobal)
        if not ptr:
            kernel32.GlobalFree(hglobal)
            return False
        try:
            ctypes.memmove(ptr, encoded, size)
        finally:
            kernel32.GlobalUnlock(hglobal)
        if not user32.SetClipboardData(CF_UNICODETEXT, hglobal):
            kernel32.GlobalFree(hglobal)
            return False
        return True
    finally:
        user32.CloseClipboard()


def clipboard_read_text() -> str | None:
    """Read OS clipboard text.

    Returns:
        Clipboard string, or None if the OS clipboard could not be read.
    """
    try:
        import pyperclip

        return pyperclip.paste()
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            return _win32_clipboard_read()
        except Exception:
            pass
    return None


def clipboard_write_text(text: str) -> bool:
    """Write text to the OS clipboard (best-effort).

    Returns:
        True if a write path reported success.
    """
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            return _win32_clipboard_write(text)
        except Exception:
            pass
    return False


def clipboard_read_files() -> list[str] | None:
    """Read OS clipboard file paths (for file copy/paste).

    Returns:
        List of file paths if clipboard contains files, otherwise None.
    """
    if sys.platform != "win32":
        # On non-Windows platforms, use pyperclip text approach
        # (file paste may be handled differently)
        try:
            import pyperclip
            text = pyperclip.paste()
            if text and "file://" in text:
                # Simple heuristic for file URLs
                import urllib.parse
                paths = []
                for line in text.splitlines():
                    if line.startswith("file://"):
                        path = urllib.parse.unquote(line[7:])
                        paths.append(path)
                if paths:
                    return paths
        except Exception:
            pass
        return None
    
    # Windows: use CF_HDROP format
    try:
        import ctypes
        
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32
        
        if not user32.OpenClipboard(None):
            return None
        
        try:
            # Check if clipboard contains CF_HDROP
            if not user32.IsClipboardFormatAvailable(CF_HDROP):
                return None
            
            handle = user32.GetClipboardData(CF_HDROP)
            if not handle:
                return None
                
            # Lock the handle to get pointer
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
                
            try:
                # Get number of files
                file_count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
                if file_count == 0:
                    return []
                
                files = []
                max_path = 260  # MAX_PATH
                buffer = ctypes.create_unicode_buffer(max_path)
                
                for i in range(file_count):
                    # Get file path
                    length = shell32.DragQueryFileW(handle, i, buffer, max_path)
                    if length > 0:
                        files.append(buffer.value)
                
                return files if files else []
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        pass
    
    return None