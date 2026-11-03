import streamlit as st
import os
import shutil
import zipfile
import tempfile
from pathlib import Path

# Проверяем доступность rarfile
try:
    import rarfile
    RAR_AVAILABLE = True
except ImportError:
    RAR_AVAILABLE = False

# ==========================================
# НАСТРОЙКИ ПО УМОЛЧАНИЮ
# ==========================================
DEFAULT_MAIL_BASE = r"W:\Poste\2026\10"
DEFAULT_REFERENCE_BASE = r"Z:\ЖКУ\Выгрузка 2026\10"
DEFAULT_OUTPUT_BASE = r"W:\Poste\2026\10\ответы жку"

EXTENSIONS = ('.xls', '.dbf', '.xlsx', '.xlsm', '.pdf')
PREFIXES = ('Z', 'O', 'o', 'о', 'О')
KEY_LENGTH = 6

# ==========================================
# ФУНКЦИИ ОБРАБОТКИ (из рабочего скрипта)
# ==========================================

def extract_key(filename):
    """Извлекает ключ из имени файла (два формата)"""
    name = os.path.splitext(filename)[0]
    
    # Формат с дефисом: ...-XXXXXX...
    if '-' in name:
        after_hyphen = name.split('-')[-1]
        if len(after_hyphen) >= KEY_LENGTH and after_hyphen[:KEY_LENGTH].isdigit():
            return after_hyphen[:KEY_LENGTH]
    
    # Формат: ..._002XXXXXX... (ищем первым, т.к. более специфичный)
    pos = name.find('_002')
    if pos != -1:
        start = pos + 4  # после "_002"
        if start + KEY_LENGTH <= len(name) and name[start:start+KEY_LENGTH].isdigit():
            return name[start:start+KEY_LENGTH]
    
    # Формат: ..._02XXXXXX...
    pos = name.find('_02')
    if pos != -1:
        start = pos + 3  # после "_02"
        if start + KEY_LENGTH <= len(name) and name[start:start+KEY_LENGTH].isdigit():
            return name[start:start+KEY_LENGTH]
    
    return None


def build_reference_dict(reference_base, progress_callback=None):
    """Построение справочника ключей из папки выгрузки"""
    ref_dict = {}
    debug_info = []
    
    if not os.path.exists(reference_base):
        return ref_dict, f"Предупреждение: справочная папка {reference_base} не найдена.", debug_info
    
    folders = [f for f in os.listdir(reference_base) if os.path.isdir(os.path.join(reference_base, f))]
    total_folders = len(folders)
    
    for idx, folder in enumerate(folders):
        folder_path = os.path.join(reference_base, folder)
        found = False
        keys_found = []
        
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(EXTENSIONS) and file.startswith(PREFIXES):
                    key = extract_key(file)
                    if key:
                        if key in ref_dict and ref_dict[key] != folder:
                            pass  # Ключ уже есть, пропускаем
                        else:
                            ref_dict[key] = folder
                            keys_found.append(key)
                        found = True
                        break
            if found:
                break
        
        status = "✅" if found else "❌"
        debug_info.append({
            'folder': folder,
            'found': found,
            'keys': keys_found,
            'status': status
        })
        
        if progress_callback:
            progress_callback((idx + 1) / total_folders)
    
    return ref_dict, None, debug_info


def process_file(src_path, ref_dict, output_base, source_label, stats, log_list):
    """Обработка одного файла"""
    file = os.path.basename(src_path)
    
    if not file.lower().endswith(EXTENSIONS):
        return
    if not file.startswith(PREFIXES):
        return
    
    key = extract_key(file)
    if not key:
        stats['no_key'] += 1
        log_list.append(f"❌ Не удалось извлечь ключ: {file}")
        return
    
    if key in ref_dict:
        org_name = ref_dict[key]
    else:
        org_name = f"Неизвестный_{key}"
        stats['unknown_keys'] += 1
        log_list.append(f"⚠️ Ключ {key} не найден: {file} -> {org_name}")
    
    dest_dir = os.path.join(output_base, org_name)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
        stats['folders_created'] += 1
        log_list.append(f"📁 Создана папка: {org_name}")
    
    dest_path = os.path.join(dest_dir, file)
    if os.path.exists(dest_path):
        base, ext = os.path.splitext(file)
        new_name = f"{base}_{source_label}{ext}"
        dest_path = os.path.join(dest_dir, new_name)
        log_list.append(f"🔄 Переименован: {file} -> {new_name}")
    
    try:
        shutil.copy2(src_path, dest_path)
        stats['copied'] += 1
        log_list.append(f"✅ Скопирован: {file} -> {org_name}")
    except Exception as e:
        log_list.append(f"❌ Ошибка копирования {file}: {e}")


def process_zip(zip_path, ref_dict, output_base, stats, log_list):
    """Обработка ZIP-архива"""
    stats['zips_total'] += 1
    log_list.append(f" Обработка ZIP: {os.path.basename(zip_path)}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            
            parent_folder = os.path.basename(os.path.dirname(zip_path))
            if not parent_folder.isdigit():
                parent_folder = 'zip'
            
            for root, dirs, files in os.walk(tmp_dir):
                for file in files:
                    src_file = os.path.join(root, file)
                    process_file(src_file, ref_dict, output_base, f"zip{parent_folder}", stats, log_list)
        except Exception as e:
            log_list.append(f"❌ Ошибка распаковки {zip_path}: {e}")


def process_rar(rar_path, ref_dict, output_base, stats, log_list):
    """Обработка RAR-архива"""
    if not RAR_AVAILABLE:
        stats['errors'] += 1
        log_list.append(f"❌ RAR не поддерживается: установите библиотеку rarfile (py -m pip install rarfile)")
        return
    
    stats['rars_total'] += 1
    log_list.append(f"📦 Обработка RAR: {os.path.basename(rar_path)}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            with rarfile.RarFile(rar_path, 'r') as rar_ref:
                rar_ref.extractall(tmp_dir)
            
            parent_folder = os.path.basename(os.path.dirname(rar_path))
            if not parent_folder.isdigit():
                parent_folder = 'rar'
            
            for root, dirs, files in os.walk(tmp_dir):
                for file in files:
                    src_file = os.path.join(root, file)
                    process_file(src_file, ref_dict, output_base, f"rar{parent_folder}", stats, log_list)
        except Exception as e:
            log_list.append(f"❌ Ошибка распаковки {rar_path}: {e}")


def process_mail(mail_base, output_base, ref_dict, progress_callback=None, log_list=None):
    """Основная обработка почтовой папки"""
    if not os.path.exists(mail_base):
        return None, f"Ошибка: почтовая папка {mail_base} не найдена."
    
    if not os.path.exists(output_base):
        os.makedirs(output_base)
    
    stats = {
        'files_total': 0,
        'zips_total': 0,
        'rars_total': 0,
        'copied': 0,
        'unknown_keys': 0,
        'no_key': 0,
        'folders_created': 0,
        'errors': 0
    }
    
    items = [i for i in os.listdir(mail_base) if not os.path.samefile(os.path.join(mail_base, i), output_base)]
    total_items = len(items)
    
    for idx, item in enumerate(items):
        item_path = os.path.join(mail_base, item)
        
        if os.path.isdir(item_path):
            for root, dirs, files in os.walk(item_path):
                for file in files:
                    src_path = os.path.join(root, file)
                    stats['files_total'] += 1
                    file_lower = file.lower()
                    if file_lower.endswith('.zip'):
                        process_zip(src_path, ref_dict, output_base, stats, log_list)
                    elif file_lower.endswith('.rar'):
                        process_rar(src_path, ref_dict, output_base, stats, log_list)
                    else:
                        label = os.path.basename(root) if root != item_path else item
                        process_file(src_path, ref_dict, output_base, label, stats, log_list)
        else:
            stats['files_total'] += 1
            item_lower = item.lower()
            if item_lower.endswith('.zip'):
                process_zip(item_path, ref_dict, output_base, stats, log_list)
            elif item_lower.endswith('.rar'):
                process_rar(item_path, ref_dict, output_base, stats, log_list)
            else:
                process_file(item_path, ref_dict, output_base, "корень", stats, log_list)
        
        if progress_callback:
            progress_callback((idx + 1) / total_items)
    
    return stats, None


# ==========================================
# ИНТЕРФЕЙС
# ==========================================

def show_interface():
    """Интерфейс для сортировки почты"""
    st.title("📧 Сортировка почты")
    st.markdown("""
    Этот инструмент собирает ответные файлы из почтовой папки и раскладывает их по папкам организаций 
    на основе справочника из папки выгрузки.
    
    **Поддерживаемые форматы:** ZIP, RAR, обычные файлы (.xls, .dbf, .xlsx, .xlsm, .pdf)
    """)
    
    # Статус поддержки RAR
    if not RAR_AVAILABLE:
        st.warning("⚠️ Библиотека `rarfile` не установлена. RAR-архивы обрабатываться не будут. Установите: `py -m pip install rarfile`")
    else:
        st.success("✅ Поддержка RAR-архивов активна")
    
    # Настройки путей
    st.markdown("### ⚙️ Настройки путей")
    
    col1, col2 = st.columns(2)
    with col1:
        mail_base = st.text_input("Почтовая папка (источник)", value=DEFAULT_MAIL_BASE)
        reference_base = st.text_input("Папка выгрузки (справочник)", value=DEFAULT_REFERENCE_BASE)
    with col2:
        output_base = st.text_input("Папка для результатов", value=DEFAULT_OUTPUT_BASE)
    
    # Проверка путей
    st.markdown("---")
    st.markdown("### 🔍 Проверка путей")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if os.path.exists(mail_base):
            st.success(f"✅ Почтовая папка найдена")
        else:
            st.error(f"❌ Почтовая папка не найдена")
    
    with col2:
        if os.path.exists(reference_base):
            st.success(f"✅ Папка выгрузки найдена")
        else:
            st.error(f"❌ Папка выгрузки не найдена")
    
    with col3:
        if os.path.exists(os.path.dirname(output_base)):
            st.success(f"✅ Родительская папка существует")
        else:
            st.warning(f"⚠️ Родительская папка не найдена (будет создана)")
    
    # Кнопка запуска
    st.markdown("---")
    if st.button("🚀 Начать сортировку", type="primary", use_container_width=True):
        
        if not os.path.exists(mail_base):
            st.error(f" Почтовая папка не найдена: {mail_base}")
            return
        
        if not os.path.exists(reference_base):
            st.error(f"❌ Папка выгрузки не найдена: {reference_base}")
            return
        
        # Этап 1: Построение справочника
        st.markdown("### 📚 Этап 1: Построение справочника ключей")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("Сканирую папку выгрузки...")
        
        def update_ref_progress(p):
            progress_bar.progress(p)
        
        ref_dict, error, debug_info = build_reference_dict(reference_base, update_ref_progress)
        
        if error:
            st.error(error)
            return
        
        progress_bar.progress(1.0)
        status_text.text(f"✅ Найдено {len(ref_dict)} уникальных ключей")
        
        # Отладочная информация
        if debug_info:
            st.markdown("---")
            st.subheader("🔍 Детали сканирования справочника")
            
            found_count = sum(1 for d in debug_info if d['found'])
            not_found_count = sum(1 for d in debug_info if not d['found'])
            
            col1, col2 = st.columns(2)
            col1.metric("Папок с файлами", found_count)
            col2.metric("Папок без файлов", not_found_count)
            
            if not_found_count > 0:
                with st.expander(f"️ Папки без файлов ({not_found_count})", expanded=False):
                    for d in debug_info:
                        if not d['found']:
                            st.text(f"  ❌ {d['folder']}")
            
            with st.expander(f"✅ Папки с файлами ({found_count})", expanded=False):
                for d in debug_info:
                    if d['found']:
                        keys_str = ", ".join(d['keys']) if d['keys'] else "—"
                        st.text(f"  ✅ {d['folder']} → ключи: {keys_str}")
        
        if not ref_dict:
            st.warning("⚠️ Справочник пуст. Все файлы будут помещены в папки 'Неизвестный_...'.")
        
        # Этап 2: Обработка почты
        st.markdown("### 📬 Этап 2: Обработка почтовой папки")
        progress_bar2 = st.progress(0)
        status_text2 = st.empty()
        
        log_list = []
        
        def update_mail_progress(p):
            progress_bar2.progress(p)
            status_text2.text(f"Обработано {int(p * 100)}%")
        
        status_text2.text("Обработка файлов...")
        stats, error = process_mail(mail_base, output_base, ref_dict, update_mail_progress, log_list)
        
        if error:
            st.error(error)
            return
        
        progress_bar2.progress(1.0)
        status_text2.text("✅ Готово!")
        
        # Показ результатов
        st.markdown("### 📊 Результаты")
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Всего файлов", stats['files_total'])
        col2.metric("Скопировано", stats['copied'])
        col3.metric("ZIP-архивов", stats['zips_total'])
        col4.metric("RAR-архивов", stats['rars_total'])
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Неизвестных ключей", stats['unknown_keys'])
        col2.metric("Без ключа", stats['no_key'])
        col3.metric("Создано папок", stats['folders_created'])
        
        if stats['errors'] > 0:
            st.warning(f"️ Ошибок: {stats['errors']}")
        
        # Логи
        with st.expander("📋 Подробный лог"):
            st.text("\n".join(log_list))