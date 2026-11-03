import streamlit as st
import os
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
import config_manager

DEFAULT_SOURCE_BASE = r"D:\выгрузка 2024"
DEFAULT_DEST_BASE = r"D:\_ЖКУ_"

# Текст напоминания
REMINDER_FILENAME = "Напоминание к файлу обмена.txt"
REMINDER_TEXT = (
    "Здравствуйте, напоминаем Вам, что при отправке нам ответных файлов "
    "необходимо оставлять название файла таким же каким он к вам приходит, "
    "либо заменяя первую букву Z на английскую O."
)


def normalize_name(name):
    name = name.replace('_', ' ').replace('-', ' ')
    name = ' '.join(name.split())
    name = name.upper()
    return name


def find_mapping_for_folder(folder_name, email_mapping):
    folder_normalized = normalize_name(folder_name)
    
    for org_name, email in email_mapping.items():
        org_normalized = normalize_name(org_name)
        if folder_normalized == org_normalized:
            return email
    
    for org_name, email in email_mapping.items():
        org_normalized = normalize_name(org_name)
        if folder_normalized in org_normalized or org_normalized in folder_normalized:
            return email
    
    return None


def create_reminder_file(dest_dir):
    """Создаёт файл-напоминание в папке, если его ещё нет"""
    reminder_path = os.path.join(dest_dir, REMINDER_FILENAME)
    
    if not os.path.exists(reminder_path):
        try:
            with open(reminder_path, 'w', encoding='utf-8') as f:
                f.write(REMINDER_TEXT)
            return True, "Файл напоминания создан"
        except Exception as e:
            return False, f"Ошибка создания файла: {e}"
    else:
        return True, "Файл напоминания уже существует"


def copy_folder_contents(src, dst, progress_callback=None, add_reminder=False):
    """Копирует содержимое папки src в dst"""
    if not os.path.exists(src):
        return 0, 0, f"ПРОПУСК: папка не найдена: {src}"
    
    os.makedirs(dst, exist_ok=True)
    
    copied = 0
    errors = 0
    log = []
    
    try:
        items = os.listdir(src)
        total = len(items)
        
        for i, item in enumerate(items):
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            
            try:
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
                copied += 1
            except Exception as e:
                errors += 1
                log.append(f"❌ {item}: {e}")
            
            if progress_callback:
                progress_callback((i + 1) / total)
        
        # Создаём файл-напоминание, если нужно
        if add_reminder:
            success, msg = create_reminder_file(dst)
            if success:
                log.append(f"📝 {msg}")
            else:
                log.append(f"⚠️ {msg}")
        
        return copied, errors, "\n".join(log)
    except Exception as e:
        return 0, 0, f"ОШИБКА: {e}"


def scan_source_folder(source_base):
    if not os.path.exists(source_base):
        return []
    
    subfolders = []
    for item in os.listdir(source_base):
        item_path = os.path.join(source_base, item)
        if os.path.isdir(item_path):
            subfolders.append(item)
    
    return sorted(subfolders)


def show_interface():
    st.title("📤 Раскладка файлов по почтовым папкам")
    st.markdown("""
    Этот инструмент копирует файлы из папок выгрузки в почтовые папки по email-адресам.
    
    **Как это работает:**
    - Вы указываете папку с выгрузкой (например, `D:\\выгрузка 2026\\11`)
    - Скрипт находит подпапки организаций в словаре
    - Копирует файлы в почтовые папки `D:\\_ЖКУ_\\email`
    - Потом эти файлы уходят через Outlook
    
    💡 **Словарь организаций берётся из файла настроек `config.json`**
    """)
    
    # Загружаем конфигурацию
    config = config_manager.load_config()
    if not config:
        st.error("❌ Файл конфигурации не найден! Перейдите в раздел **⚙️ Настройки** и настройте приложение.")
        return
    
    email_mapping = config.get("email_mapping", {})
    paths = config.get("paths", {})
    
    # Инициализируем session_state для путей
    if "adler_source" not in st.session_state:
        st.session_state.adler_source = paths.get("adler_source", DEFAULT_SOURCE_BASE)
    if "adler_dest" not in st.session_state:
        st.session_state.adler_dest = paths.get("adler_dest", DEFAULT_DEST_BASE)
    if "add_reminder" not in st.session_state:
        st.session_state.add_reminder = False
    
    # Настройки путей
    st.markdown("### ️ Настройки путей")
    
    col1, col2 = st.columns(2)
    with col1:
        source_base = st.text_input(
            "📂 Папка с выгрузкой (источник)",
            value=st.session_state.adler_source,
            key="input_adler_source",
            help="Папка, внутри которой лежат подпапки организаций"
        )
    with col2:
        dest_base = st.text_input(
            "📁 Базовая папка назначения",
            value=st.session_state.adler_dest,
            key="input_adler_dest",
            help="Базовая папка, куда будут копироваться файлы"
        )
    
    # Чекбокс для файла-напоминания
    st.markdown("---")
    st.markdown("###  Дополнительные опции")
    
    add_reminder = st.checkbox(
        "📄 Добавлять файл-напоминание в каждую папку",
        value=st.session_state.add_reminder,
        help="В каждую папку назначения будет добавлен текстовый файл с напоминанием о правильном именовании файлов"
    )
    
    # Сохраняем состояние чекбокса
    st.session_state.add_reminder = add_reminder
    
    if add_reminder:
        with st.expander("👁️ Посмотреть текст напоминания", expanded=False):
            st.text_area("Содержание файла:", REMINDER_TEXT, height=100)
            st.info(f"📄 Имя файла: `{REMINDER_FILENAME}`")
    
    # Кнопка сохранения путей
    if st.button("💾 Сохранить пути", use_container_width=True):
        st.session_state.adler_source = source_base
        st.session_state.adler_dest = dest_base
        
        paths["adler_source"] = source_base
        paths["adler_dest"] = dest_base
        config["paths"] = paths
        config_manager.save_config(config)
        
        st.success("✅ Пути сохранены!")
        st.rerun()
    
    # Показываем статистику словаря
    st.markdown("---")
    st.markdown("### 📋 Словарь организаций")
    
    if email_mapping:
        st.success(f"✅ В словаре: **{len(email_mapping)}** организаций")
        
        with st.expander("👁️ Показать список организаций", expanded=False):
            for org_name, email in sorted(email_mapping.items()):
                st.text(f"  🏢 {org_name} → 📧 {email}")
    else:
        st.warning("⚠️ Словарь пуст! Добавьте организации в разделе **⚙️ Настройки**")
    
    # Проверка путей
    st.markdown("---")
    st.markdown("### 🔍 Проверка путей")
    
    col1, col2 = st.columns(2)
    with col1:
        if os.path.exists(source_base):
            st.success(f"✅ Папка-источник найдена")
            subfolders = scan_source_folder(source_base)
            st.info(f" Найдено подпапок: **{len(subfolders)}**")
        else:
            st.error(f"❌ Папка-источник не найдена")
            subfolders = []
    
    with col2:
        if os.path.exists(dest_base):
            st.success(f"✅ Папка назначения найдена")
        else:
            st.warning(f"️ Папка назначения не найдена (будет создана)")
    
    # Предпросмотр
    if subfolders and email_mapping:
        st.markdown("---")
        st.markdown("### 📋 Предпросмотр: какие папки будут обработаны")
        
        found_folders = []
        not_found_folders = []
        
        for folder in subfolders:
            email = find_mapping_for_folder(folder, email_mapping)
            if email:
                found_folders.append((folder, email))
            else:
                not_found_folders.append(folder)
        
        col1, col2 = st.columns(2)
        with col1:
            st.success(f"✅ Будут обработаны: **{len(found_folders)}** папок")
            if found_folders:
                with st.expander("Показать список", expanded=False):
                    for folder, email in found_folders:
                        st.text(f"  • {folder} → {email}")
        
        with col2:
            if not_found_folders:
                st.warning(f"⚠️ Не найдены в словаре: **{len(not_found_folders)}** папок")
                with st.expander("Показать список", expanded=False):
                    for folder in not_found_folders:
                        st.text(f"  • {folder}")
            else:
                st.success("✅ Все папки найдены в словаре!")
        
        # Кнопка запуска
        st.markdown("---")
        if st.button("🚀 Начать раскладку", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total_pairs = len(found_folders)
            total_copied = 0
            total_errors = 0
            reminders_created = 0
            all_logs = []
            
            for i, (folder, email) in enumerate(found_folders):
                src = os.path.join(source_base, folder)
                dst = os.path.join(dest_base, email)
                
                status_text.text(f"Обработка {i+1}/{total_pairs}: {folder}")
                
                def update_progress(p):
                    overall_progress = (i + p) / total_pairs
                    progress_bar.progress(overall_progress)
                
                copied, errors, log = copy_folder_contents(
                    src, dst, update_progress, add_reminder=add_reminder
                )
                total_copied += copied
                total_errors += errors
                
                if add_reminder:
                    reminders_created += 1
                
                all_logs.append(f"\n{'='*60}\n{folder} → {email}\nСкопировано: {copied}, Ошибок: {errors}")
                if log:
                    all_logs.append(log)
            
            progress_bar.progress(1.0)
            status_text.text("✅ Готово!")
            
            # Показ результатов
            st.success(f"✅ Завершено! Скопировано: {total_copied}, Ошибок: {total_errors}")
            
            if add_reminder:
                st.info(f"📄 Файлов-напоминаний добавлено: **{reminders_created}**")
            
            if not_found_folders:
                st.warning(f"⚠️ Пропущено папок (не найдены в словаре): {len(not_found_folders)}")
                for folder in not_found_folders:
                    st.text(f"  • {folder}")
            
            with st.expander("📋 Подробный лог"):
                st.text("\n".join(all_logs))