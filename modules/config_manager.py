import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

def load_config():
    """Загружает конфигурацию из файла"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_config(config):
    """Сохраняет конфигурацию в файл"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

def get_default_config():
    """Возвращает конфигурацию по умолчанию"""
    return {
        "paths": {
            "root_folder": "Z:\\ЖКУ",
            "mail_base": "W:\\Poste\\2026\\10",
            "reference_base": "Z:\\ЖКУ\\Выгрузка 2026\\10",
            "output_base": "W:\\Poste\\2026\\10\\ответы жку",
            "adler_source": "D:\\выгрузка 2024",
            "adler_dest": "D:\\_ЖКУ_"
        },
        "email_mapping": {},
        "app_settings": {
            "theme": "dark",
            "language": "ru",
            "auto_scan": False
        }
    }

def export_config():
    """Экспортирует конфигурацию в файл для передачи коллеге"""
    config = load_config()
    if config:
        export_file = Path(__file__).parent.parent / "config_export.json"
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return export_file
    return None

def import_config(file_path):
    """Импортирует конфигурацию из файла"""
    with open(file_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    save_config(config)
    return True

def get_email_mapping():
    """Возвращает только словарь email_mapping"""
    config = load_config()
    if config:
        return config.get("email_mapping", {})
    return {}

def add_organization(name, email, contact_person=""):
    """Добавляет организацию в config.json"""
    config = load_config()
    if not config:
        config = get_default_config()
    
    email_mapping = config.get("email_mapping", {})
    
    # Проверяем дубликат
    if name in email_mapping:
        return False, "Организация с таким названием уже существует"
    
    email_mapping[name] = email
    config["email_mapping"] = email_mapping
    save_config(config)
    return True, "Организация добавлена"

def update_organization(name, email=None, contact_person=None):
    """Обновляет данные организации в config.json"""
    config = load_config()
    if not config:
        return False, "Конфигурация не найдена"
    
    email_mapping = config.get("email_mapping", {})
    
    if name not in email_mapping:
        return False, "Организация не найдена"
    
    if email is not None:
        email_mapping[name] = email
    
    config["email_mapping"] = email_mapping
    save_config(config)
    return True, "Организация обновлена"

def import_organizations(records, mode="merge"):
    """Массовая загрузка организаций из списка словарей [{'name','email','contact_person'}].

    mode == "merge"  — дополняет справочник: новые добавляются,
                       существующие обновляют email/контакт, если пришли непустые значения.
    mode == "replace" — полностью заменяет справочник organizations переданными данными.

    Возвращает: (stats, errors), где stats = {"added", "updated", "skipped", "total"}
    """
    if mode == "replace":
        email_mapping = {}
    else:
        config = load_config() or get_default_config()
        email_mapping = config.get("email_mapping", {})

    added = updated = skipped = 0
    errors = []

    for i, rec in enumerate(records, start=1):
        name = str(rec.get("name") or "").strip()
        email = str(rec.get("email") or "").strip().lower()
        contact = str(rec.get("contact_person") or "").strip()

        if not name:
            errors.append(f"Строка {i}: пустое название организации")
            continue
        if "@" not in email:
            errors.append(f"Строка {i} («{name}»): некорректный email «{email}»")
            continue

        if name in email_mapping:
            new_email = email if email else None
            if new_email and new_email != email_mapping[name]:
                email_mapping[name] = new_email
                updated += 1
            else:
                skipped += 1
        else:
            email_mapping[name] = email
            added += 1

        # контакт сохраняем в БД (если строка валидна)
        try:
            _update_contact_in_db(name, contact)
        except Exception:
            pass

    config = load_config() or get_default_config()
    config["email_mapping"] = email_mapping
    save_config(config)

    return {"added": added, "updated": updated, "skipped": skipped,
            "total": added + updated + skipped}, errors


def _update_contact_in_db(name, contact):
    """Обновляет контактное лицо организации в базе данных (если она там есть)."""
    import sqlite3
    from pathlib import Path as _Path
    db_file = _Path(__file__).parent.parent / "zhku_database.db"
    if not db_file.exists():
        return
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM organizations WHERE name = ?', (name,))
    row = cursor.fetchone()
    if row:
        if contact:
            cursor.execute('UPDATE organizations SET contact_person = ? WHERE name = ?',
                           (contact, name))
    else:
        cursor.execute('INSERT INTO organizations (name, email, contact_person) VALUES (?, ?, ?)',
                       (name, "", contact))
    conn.commit()
    conn.close()


def delete_organization(name):
    """Удаляет организацию из config.json"""
    config = load_config()
    if not config:
        return False, "Конфигурация не найдена"
    
    email_mapping = config.get("email_mapping", {})
    
    if name not in email_mapping:
        return False, "Организация не найдена"
    
    del email_mapping[name]
    config["email_mapping"] = email_mapping
    save_config(config)
    return True, "Организация удалена"

def get_all_organizations():
    """Возвращает список всех организаций из config.json"""
    email_mapping = get_email_mapping()
    return [{"name": name, "email": email} for name, email in email_mapping.items()]