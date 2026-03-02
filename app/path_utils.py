import os
import sys

def get_base_dir() -> str:
    """Zwraca katalog bazowy dla plików aplikacji (działa również po zbudowaniu przez PyInstaller)"""
    if getattr(sys, 'frozen', False):
        # Aplikacja zbudowana (PyInstaller --onefile) - powrót do katalogu uruchomienia by vendor/ był obok binarki
        return os.path.dirname(sys.executable)
    # Aplikacja uruchamiana normalnie (zakładamy wywołanie z głównego folderu lub że jesteśmy w podkatalogu app)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
