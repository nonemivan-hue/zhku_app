import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import plotly.express as px
import io
import re
from datetime import datetime
import sys
import os

# Импортируем config_manager
sys.path.insert(0, str(Path(__file__).parent))
import config_manager

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
DB_NAME = "zhku_database.db"

# Путь берём из config.json, если нет — по умолчанию
def get_root_folder():
    config = config_manager.load_config()
    if config:
        return Path(config.get("paths", {}).get("root_folder", r"Z:\ЖКУ"))
    return Path(r"Z:\ЖКУ")

# ==========================================
# 2. ФУНКЦИИ НОРМАЛИЗАЦИИ
# ==========================================

def normalize_name(name):
    """Нормализует название: заменяет подчёркивания/дефисы на пробелы, убирает лишние пробелы"""
    name = name.replace('_', ' ').replace('-', ' ')
    name = ' '.join(name.split())
    name = name.upper()
    return name


def find_canonical_name(folder_name, email_mapping):
    """Ищет соответствие папки в словаре email_mapping"""
    folder_normalized = normalize_name(folder_name)
    
    # Точное совпадение
    for org_name, email in email_mapping.items():
        org_normalized = normalize_name(org_name)
        if folder_normalized == org_normalized:
            return org_name, email
    
    # Частичное совпадение
    for org_name, email in email_mapping.items():
        org_normalized = normalize_name(org_name)
        if folder_normalized in org_normalized or org_normalized in folder_normalized:
            return org_name, email
    
    # Если не нашли — возвращаем нормализованное название папки
    return folder_name.strip('_').title(), None


# ==========================================
# 3. РАБОТА С БАЗОЙ ДАННЫХ
# ==========================================

def init_db():
    """Создает таблицы и заполняет организации из config.json"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            email TEXT,
            contact_person TEXT,
            merged_into_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (merged_into_id) REFERENCES organizations(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_name TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            month_year TEXT NOT NULL,
            status TEXT NOT NULL,
            file_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(org_name, file_type, month_year)
        )
    ''')
    
    # Заполняем организации из config.json
    email_mapping = config_manager.get_email_mapping()
    for org_name, email in email_mapping.items():
        cursor.execute('''
            INSERT INTO organizations (name, email) 
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET email=excluded.email
        ''', (org_name, email))
    
    conn.commit()
    conn.close()


def get_canonical_org_name(name, conn):
    """Проверяет, не является ли название синонимом другой организации"""
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, merged_into_id FROM organizations WHERE name = ?
    ''', (name,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute('''
            SELECT id, name, merged_into_id FROM organizations 
            WHERE UPPER(name) = UPPER(?)
        ''', (name,))
        row = cursor.fetchone()
    
    if not row:
        return name
    
    org_id, org_name, merged_into_id = row
    if merged_into_id:
        cursor.execute('SELECT name FROM organizations WHERE id = ?', (merged_into_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
    return org_name


def scan_folders():
    """Сканирует папки Выгрузка и Загрузка"""
    ROOT_FOLDER = get_root_folder()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM files")
    
    email_mapping = config_manager.get_email_mapping()
    
    files_processed = 0
    orgs_found = set()
    
    for year_folder in ROOT_FOLDER.iterdir():
        if not year_folder.is_dir():
            continue
        
        year_match = re.search(r'(20\d{2})', year_folder.name)
        if not year_match:
            continue
        
        year = year_match.group(1)
        folder_name_lower = year_folder.name.lower()
        
        if 'выгрузка' in folder_name_lower:
            file_type = 'Выгрузка'
        elif 'загрузка' in folder_name_lower:
            file_type = 'Загрузка'
        else:
            continue
        
        for month_folder in sorted(year_folder.iterdir()):
            if not month_folder.is_dir():
                continue
            
            month_num = month_folder.name.strip()
            if month_num.isdigit() and 1 <= int(month_num) <= 12:
                month_year = f"{year}-{int(month_num):02d}"
            else:
                continue
            
            for org_folder in month_folder.iterdir():
                if not org_folder.is_dir():
                    continue
                
                org_name_raw = org_folder.name
                
                # Ищем соответствие в словаре из config.json
                canonical_name, email = find_canonical_name(org_name_raw, email_mapping)
                canonical_name = get_canonical_org_name(canonical_name, conn)
                orgs_found.add(canonical_name)
                
                cursor.execute('''
                    INSERT OR IGNORE INTO organizations (name) VALUES (?)
                ''', (canonical_name,))
                
                if email:
                    cursor.execute('''
                        UPDATE organizations SET email = ? WHERE name = ?
                    ''', (email, canonical_name))
                
                for file_path in org_folder.rglob('*'):
                    if file_path.is_file() and not file_path.name.startswith('~$'):
                        try:
                            cursor.execute('''
                                INSERT OR REPLACE INTO files 
                                (org_name, file_name, file_type, month_year, status, file_path)
                                VALUES (?, ?, ?, ?, 'Получен', ?)
                            ''', (canonical_name, file_path.name, file_type, month_year, str(file_path)))
                            files_processed += 1
                        except Exception as e:
                            print(f"Ошибка: {file_path} - {e}")
    
    conn.commit()
    conn.close()
    return files_processed, len(orgs_found)


# ==========================================
# 4. КЭШИРОВАННЫЕ ФУНКЦИИ (для скорости)
# ==========================================

@st.cache_data(ttl=30)  # Кэш на 30 секунд
def load_data_cached():
    """Загружает данные из БД с кэшированием"""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM files ORDER BY month_year DESC, org_name", conn)
    conn.close()
    return df


@st.cache_data(ttl=60)  # Кэш на 60 секунд
def get_all_organizations_cached():
    """Получает все организации из config.json с кэшированием"""
    return config_manager.get_all_organizations()


def load_data():
    """Загружает данные из БД (без кэша — для принудительного обновления)"""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM files ORDER BY month_year DESC, org_name", conn)
    conn.close()
    return df


def get_missing_organizations(month_year):
    """Находит организации, которые не прислали файлы"""
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT DISTINCT f.org_name, o.email, o.contact_person
        FROM files f
        LEFT JOIN organizations o ON f.org_name = o.name
        WHERE f.month_year = ? AND f.file_type = 'Выгрузка'
        AND f.org_name NOT IN (
            SELECT org_name FROM files 
            WHERE month_year = ? AND file_type = 'Загрузка'
        )
        ORDER BY f.org_name
    '''
    df = pd.read_sql_query(query, conn, params=(month_year, month_year))
    conn.close()
    return df


def get_all_organizations():
    """Получает все организации из config.json"""
    return config_manager.get_all_organizations()


def update_organization_in_db(org_name, email, contact_person):
    """Обновляет данные организации в БД"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE organizations
        SET email = ?, contact_person = ?
        WHERE name = ?
    ''', (email, contact_person, org_name))
    conn.commit()
    conn.close()


def delete_organization_from_db(org_name):
    """Удаляет организацию из БД"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM files WHERE org_name = ?', (org_name,))
    cursor.execute('DELETE FROM organizations WHERE name = ?', (org_name,))
    conn.commit()
    conn.close()


def get_duplicate_suggestions():
    """Находит похожие названия"""
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT name FROM organizations 
        WHERE merged_into_id IS NULL
        ORDER BY name
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    STOP_WORDS = {
        'ООО', 'УК', 'ТСЖ', 'ТСН', 'АО', 'ПАО', 'СНТ', 'ИП', 'НУ', 'НФУ', 
        'МУП', 'ФГБНУ', 'ФГУП', 'ФГАУ', 'ЖК', 'СЕРВИС', 'УПРАВЛЯЮЩАЯ', 
        'КОМПАНИЯ', 'ОРГАНИЗАЦИЯ', 'ОБЩЕСТВО'
    }
    
    suggestions = []
    names = df['name'].tolist()
    
    for i, name1 in enumerate(names):
        for name2 in names[i+1:]:
            words1 = name1.upper().split()
            words2 = name2.upper().split()
            words1_filtered = {w for w in words1 if w not in STOP_WORDS}
            words2_filtered = {w for w in words2 if w not in STOP_WORDS}
            common_words = words1_filtered & words2_filtered
            
            if len(common_words) >= 2:
                suggestions.append((name1, name2, list(common_words)))
    
    return suggestions


def merge_organizations(source_name, target_name):
    """Объединяет две организации"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT id FROM organizations WHERE name = ?', (target_name,))
        target_row = cursor.fetchone()
        if not target_row:
            conn.close()
            return False, "Целевая организация не найдена"
        
        target_id = target_row[0]
        
        cursor.execute('''
            DELETE FROM files 
            WHERE org_name = ? 
            AND (file_type, month_year) IN (
                SELECT file_type, month_year FROM files WHERE org_name = ?
            )
        ''', (source_name, target_name))
        
        cursor.execute('''
            UPDATE files SET org_name = ? WHERE org_name = ?
        ''', (target_name, source_name))
        
        cursor.execute('''
            UPDATE organizations SET merged_into_id = ? WHERE name = ?
        ''', (target_id, source_name))
        
        conn.commit()
        conn.close()
        return True, "Организации объединены"
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e)


def auto_merge_organizations(threshold=2):
    """Автоматически объединяет организации с высоким совпадением"""
    suggestions = get_duplicate_suggestions()
    merged_count = 0
    errors = []
    
    for name1, name2, common_words in suggestions:
        if len(common_words) >= threshold:
            if len(name1) <= len(name2):
                target, source = name1, name2
            else:
                target, source = name2, name1
            
            success, msg = merge_organizations(source, target)
            if success:
                merged_count += 1
            else:
                errors.append(f"{source} → {target}: {msg}")
    
    return merged_count, errors


def unmerge_organizations(org_name):
    """Разъединяет организацию"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE organizations SET merged_into_id = NULL WHERE name = ?
        ''', (org_name,))
        
        conn.commit()
        conn.close()
        return True, "Организация разъединена"
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, str(e)


def get_merged_organizations():
    """Получает список объединённых организаций"""
    conn = sqlite3.connect(DB_NAME)
    query = '''
        SELECT o1.name as synonym_name, o2.name as main_name
        FROM organizations o1
        JOIN organizations o2 ON o1.merged_into_id = o2.id
        ORDER BY o2.name, o1.name
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


# ==========================================
# 5. ИНТЕРФЕЙС
# ==========================================

def show_dashboard():
    """Вкладка: Дашборд — оптимизированная версия"""
    st.title("📊 Дашборд")
    
    if st.button("🔄 Обновить данные", type="primary"):
        with st.spinner("Сканирую папки..."):
            files_count, orgs_count = scan_folders()
        st.success(f"✅ Найдено: {files_count} файлов от {orgs_count} организаций")
        load_data_cached.clear()
        st.rerun()
    
    df = load_data()
    
    if df.empty:
        st.warning("📭 База данных пуста. Нажмите кнопку 'Обновить данные'.")
        st.info(f"💾 Путь для сканирования: `{get_root_folder()}`")
        return
    
    all_orgs_from_config = get_all_organizations_cached()
    
    # Фильтры
    col1, col2 = st.columns([1, 3])
    with col1:
        st.markdown("### 🔍 Фильтры")
        search = st.text_input("Поиск", "")
        all_months = sorted(df['month_year'].unique(), reverse=True)
        selected_months = st.multiselect("Месяц", all_months, default=[all_months[0]] if all_months else [])
        all_orgs = sorted(df['org_name'].unique())
        selected_orgs = st.multiselect("Организация", all_orgs)
    
    with col2:
        # Оптимизация: не копируем весь df, а работаем с фильтрованным
        filtered_df = df
        if search:
            mask = (
                filtered_df['org_name'].str.contains(search, case=False, na=False) |
                filtered_df['file_name'].str.contains(search, case=False, na=False)
            )
            filtered_df = filtered_df[mask]
        if selected_months:
            filtered_df = filtered_df[filtered_df['month_year'].isin(selected_months)]
        if selected_orgs:
            filtered_df = filtered_df[filtered_df['org_name'].isin(selected_orgs)]
        
        # Метрики
        st.markdown("### 📊 Статистика")
        col1, col2, col3, col4 = st.columns(4)
        vygruzka_count = len(filtered_df[filtered_df['file_type'] == 'Выгрузка'])
        zagruzka_count = len(filtered_df[filtered_df['file_type'] == 'Загрузка'])
        col1.metric("Всего файлов", len(filtered_df))
        col2.metric("Организаций", filtered_df['org_name'].nunique())
        col3.metric("📤 Выгрузка", vygruzka_count)
        col4.metric("📥 Загрузка", zagruzka_count)
        
        # ==========================================
        # ОПТИМИЗИРОВАННЫЕ ДАШБОРДЫ
        # ==========================================
        
               # 1. Статус за текущий месяц (исправленная логика)
        if all_months:
            current_month = all_months[0]
            current_month_df = df[df['month_year'] == current_month]
            
            # Считаем организации в Выгрузке (от кого ждём ответы)
            orgs_in_vygruzka = current_month_df[current_month_df['file_type'] == 'Выгрузка']['org_name'].nunique()
            
            # Считаем организации в Загрузке (кто фактически прислал)
            orgs_in_zagruzka = current_month_df[current_month_df['file_type'] == 'Загрузка']['org_name'].nunique()
            
            # Не прислали = Выгрузка - Загрузка
            orgs_not_responded = max(0, orgs_in_vygruzka - orgs_in_zagruzka)
            
            # Заполненность = Загрузка / Выгрузка * 100
            completion_percentage = (orgs_in_zagruzka / orgs_in_vygruzka * 100) if orgs_in_vygruzka > 0 else 0
            
            st.markdown("---")
            st.subheader(f"📅 Статус за {current_month}")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Ожидаем ответов", orgs_in_vygruzka)
            col2.metric("Прислали файлы", orgs_in_zagruzka)
            col3.metric("Не прислали", orgs_not_responded)
            
            st.progress(completion_percentage / 100)
            
            status_text = f"✅ Прислали: {orgs_in_zagruzka} | ❌ Не прислали: {orgs_not_responded} | 📊 Заполненность: {completion_percentage:.0f}%"
            st.info(status_text)
        
               # 2. Динамика по месяцам (столбчатая диаграмма + таблица)
        st.markdown("---")
        st.subheader("📊 Динамика по месяцам")
        
        # Группируем данные по месяцу и типу
        month_stats = df.groupby(['month_year', 'file_type']).size().unstack(fill_value=0)
        
        # Добавляем колонку с процентом выполнения
        if 'Выгрузка' in month_stats.columns and 'Загрузка' in month_stats.columns:
            month_stats['Выполнение %'] = (
                month_stats['Загрузка'] / month_stats['Выгрузка'] * 100
            ).round(0).astype(int)
        elif 'Выгрузка' in month_stats.columns:
            month_stats['Выполнение %'] = 0
        elif 'Загрузка' in month_stats.columns:
            month_stats['Выполнение %'] = 100
        
        # Сортируем по месяцу
        month_stats = month_stats.sort_index()
        
        # Столбчатая диаграмма (встроенная — быстрая)
        chart_data = month_stats[['Выгрузка', 'Загрузка']].copy()
        st.bar_chart(chart_data, height=300)
        
        # Таблица со статистикой по месяцам
        st.markdown("### 📋 Детализация по месяцам")
        
        display_table = month_stats.copy()
        display_table.columns = [
            '📤 Выгрузка', 
            '📥 Загрузка', 
            '✅ Выполнение'
        ]
        
        # Форматируем процент
        display_table['✅ Выполнение'] = display_table['✅ Выполнение'].apply(
            lambda x: f"{x}%" if pd.notna(x) else "—"
        )
        
        st.dataframe(display_table, use_container_width=True, height=250)
        
        # 3. Последние поступления (таблица)
        st.markdown("---")
        st.subheader("🕐 Последние поступления")
        
        recent_files = df.sort_values('created_at', ascending=False).head(10)
        recent_display = recent_files[['org_name', 'file_name', 'file_type', 'month_year', 'created_at']].copy()
        recent_display.columns = ['Организация', 'Файл', 'Тип', 'Месяц', 'Дата получения']
        recent_display['Дата получения'] = pd.to_datetime(recent_display['Дата получения']).dt.strftime('%d.%m.%Y %H:%M')
        
        st.dataframe(recent_display, use_container_width=True, height=250)
        
                # 4. Просроченные организации (кто не прислал за текущий месяц)
        if all_months and orgs_in_vygruzka > 0:
            current_month = all_months[0]
            current_month_files = df[df['month_year'] == current_month]
            
            # Организации в Выгрузке (от кого ждём ответы)
            orgs_vygruzka_list = current_month_files[current_month_files['file_type'] == 'Выгрузка']['org_name'].unique()
            
            # Организации в Загрузке (кто прислал)
            orgs_zagruzka_list = current_month_files[current_month_files['file_type'] == 'Загрузка']['org_name'].unique()
            
            # Те, кто не прислал = Выгрузка - Загрузка
            orgs_not_responded_list = [org for org in orgs_vygruzka_list if org not in orgs_zagruzka_list]
            
            if orgs_not_responded_list:
                st.markdown("---")
                st.subheader(f"️ Не прислали файлы за {current_month} ({len(orgs_not_responded_list)})")
                
                not_responded_df = pd.DataFrame({'Организация': orgs_not_responded_list})
                
                email_dict = {org['name']: org.get('email', '') for org in all_orgs_from_config}
                not_responded_df['Email'] = not_responded_df['Организация'].map(email_dict).fillna('Не указан')
                
                st.dataframe(not_responded_df, use_container_width=True, height=300)
                
                emails = [email_dict.get(org, '') for org in orgs_not_responded_list if email_dict.get(org)]
                if emails:
                    emails_str = '; '.join(emails)
                    st.markdown("###  Быстрые действия")
                    st.text_area("Скопируйте email для рассылки:", emails_str, height=100)
        
        # 5. Реестр файлов
        st.markdown("---")
        st.subheader("📋 Реестр файлов")
        display_df = filtered_df[['org_name', 'file_name', 'file_type', 'month_year']].copy()
        display_df.columns = ['Организация', 'Имя файла', 'Тип', 'Месяц']
        st.dataframe(display_df, use_container_width=True, height=400)

def show_control():
    """Вкладка: Контроль"""
    st.title("⚠️ Контроль: кто не прислал файлы")
    st.markdown("Организации, которые есть в **Выгрузке**, но отсутствуют в **Загрузке** за выбранный месяц.")
    
    df = load_data()
    if df.empty:
        st.warning("📭 База данных пуста.")
        return
    
    all_months = sorted(df['month_year'].unique(), reverse=True)
    selected_month = st.selectbox("Выберите месяц для проверки", all_months)
    
    missing_df = get_missing_organizations(selected_month)
    
    if missing_df.empty:
        st.success(f"✅ За {selected_month} все организации прислали файлы!")
    else:
        st.warning(f"⚠️ За {selected_month} не прислали файлы: **{len(missing_df)} организаций**")
        
        display_cols = ['org_name']
        if 'email' in missing_df.columns:
            display_cols.append('email')
        if 'contact_person' in missing_df.columns:
            display_cols.append('contact_person')
        
        display_missing = missing_df[display_cols].copy()
        display_missing.columns = ['Организация'] + (['Email'] if 'email' in display_cols else []) + (['Контактное лицо'] if 'contact_person' in display_cols else [])
        st.dataframe(display_missing, use_container_width=True, height=300)
        
        if 'email' in missing_df.columns and not missing_df['email'].isna().all():
            emails = missing_df['email'].dropna().tolist()
            emails_str = '; '.join(emails)
            st.markdown("### 📋 Быстрые действия")
            col1, col2 = st.columns(2)
            with col1:
                st.text_area("Скопируйте email для рассылки:", emails_str, height=100)
            with col2:
                st.markdown(f"**Всего email для рассылки:** {len(emails)}")
                st.info("💡 Выделите текст слева и скопируйте (Ctrl+C)")


def show_directory():
    """Вкладка: Справочник"""
    st.title("📇 Справочник организаций")
    
    # Получаем организации из config.json (кэшировано)
    orgs_list = get_all_organizations_cached()
    
    if not orgs_list:
        st.info("📭 Справочник пуст. Добавьте организации через форму ниже или в разделе **⚙️ Настройки**.")
    else:
        st.markdown(f"**Всего организаций в базе:** {len(orgs_list)}")
    
    # ==========================================
    # ДОБАВЛЕНИЕ НОВОЙ ОРГАНИЗАЦИИ
    # ==========================================
    st.markdown("---")
    st.subheader(" Добавить новую организацию")
    
    if "new_org_name" not in st.session_state:
        st.session_state.new_org_name = ""
    if "new_org_email" not in st.session_state:
        st.session_state.new_org_email = ""
    
    col1, col2 = st.columns(2)
    with col1:
        new_name = st.text_input(
            "Название организации", 
            value=st.session_state.new_org_name,
            key="dir_new_org",
            placeholder="Например: ООО Новая УК"
        )
    with col2:
        new_email = st.text_input(
            "Email", 
            value=st.session_state.new_org_email,
            key="dir_new_email",
            placeholder="Например: new-uk@mail.ru"
        )
    
    if st.button("➕ Добавить", type="primary", use_container_width=True):
        if not new_name.strip():
            st.error("❌ Введите название организации")
        elif not new_email.strip():
            st.error("❌ Введите email")
        else:
            success, msg = config_manager.add_organization(new_name.strip(), new_email.strip())
            if success:
                # Добавляем в БД
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO organizations (name, email) 
                    VALUES (?, ?)
                    ON CONFLICT(name) DO UPDATE SET email=excluded.email
                ''', (new_name.strip(), new_email.strip()))
                conn.commit()
                conn.close()
                
                # Очищаем кэш организаций
                get_all_organizations_cached.clear()
                
                st.success(f"✅ {msg}: '{new_name.strip()}'")
                st.session_state.new_org_name = ""
                st.session_state.new_org_email = ""
                st.rerun()
            else:
                st.warning(f"⚠️ {msg}")
    
    # ==========================================
    # РЕДАКТИРОВАНИЕ СУЩЕСТВУЮЩЕЙ
    # ==========================================
    if orgs_list:
        st.markdown("---")
        st.subheader("✏️ Редактировать организацию")
        
        org_names = [org['name'] for org in orgs_list]
        selected_org = st.selectbox("Выберите организацию", [""] + org_names)
        
        if selected_org:
            current_org = next((org for org in orgs_list if org['name'] == selected_org), None)
            current_email = current_org['email'] if current_org else ""
            
            # Получаем contact_person из БД
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('SELECT contact_person FROM organizations WHERE name = ?', (selected_org,))
            row = cursor.fetchone()
            conn.close()
            current_contact = row[0] if row and row[0] else ""
            
            col1, col2 = st.columns(2)
            with col1:
                new_email = st.text_input("Email", value=current_email)
            with col2:
                new_contact = st.text_input("Контактное лицо", value=current_contact)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Сохранить", use_container_width=True):
                    config_manager.update_organization(selected_org, email=new_email)
                    update_organization_in_db(selected_org, new_email, new_contact)
                    get_all_organizations_cached.clear()
                    st.success(f"✅ Данные для '{selected_org}' обновлены!")
                    st.rerun()
            with col2:
                if st.button("🗑️ Удалить", use_container_width=True):
                    if st.session_state.get(f"confirm_del_{selected_org}"):
                        config_manager.delete_organization(selected_org)
                        delete_organization_from_db(selected_org)
                        get_all_organizations_cached.clear()
                        st.success(f"✅ Организация '{selected_org}' удалена!")
                        st.session_state[f"confirm_del_{selected_org}"] = False
                        st.rerun()
                    else:
                        st.session_state[f"confirm_del_{selected_org}"] = True
                        st.warning(f"⚠️ Нажмите ещё раз для подтверждения удаления '{selected_org}'")
        
        # ==========================================
        # ТАБЛИЦА ВСЕХ ОРГАНИЗАЦИЙ
        # ==========================================
        st.markdown("---")
        st.subheader("📋 Все организации")
        
        df_orgs = pd.DataFrame(orgs_list)
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        contact_data = {}
        for org in orgs_list:
            cursor.execute('SELECT contact_person FROM organizations WHERE name = ?', (org['name'],))
            row = cursor.fetchone()
            contact_data[org['name']] = row[0] if row and row[0] else ""
        conn.close()
        
        df_orgs['contact_person'] = df_orgs['name'].map(contact_data)
        
        st.dataframe(df_orgs[['name', 'email', 'contact_person']], use_container_width=True, height=400)


# ==========================================
#  ЗАГРУЗКА СПРАВОЧНИКОВ (импорт из файлов)
# ==========================================

# Варианты названий колонок в загружаемых файлах
REF_NAME_ALIASES = ["name", "название", "организация", "наименование",
                    "уо", "управляющая организация", "ук", "поставщик", "адресат"]
REF_EMAIL_ALIASES = ["email", "e-mail", "почта", "электронная почта",
                     "эл. почта", "адрес почты", "mail"]
REF_CONTACT_ALIASES = ["contact", "contact_person", "контакт", "контактное лицо",
                       "ответственный", "физлицо"]


def _find_column(columns, aliases):
    """Ищет колонку по списку возможных названий (без учёта регистра/пробелов)."""
    norm_cols = {re.sub(r"[\s_\-\.]+", " ", str(c).strip().lower()): c for c in columns}
    for alias in aliases:
        key = re.sub(r"[\s_\-\.]+", " ", alias.lower())
        if key in norm_cols:
            return norm_cols[key]
    # частичное совпадение
    for alias in aliases:
        key = re.sub(r"[\s_\-\.]+", " ", alias.lower())
        for norm_c, orig_c in norm_cols.items():
            if key in norm_c or norm_c in key:
                return orig_c
    return None


def parse_reference_file(uploaded_file):
    """Читает файл справочника (xlsx/xls/ods/csv/txt/json) и возвращает DataFrame
    с нормализованными колонками name / email / contact_person."""
    ext = uploaded_file.name.rsplit(".", 1)[-1].lower()
    data = uploaded_file.getvalue()

    if ext == "json":
        import json as _json
        obj = _json.loads(data.decode("utf-8-sig"))
        if isinstance(obj, dict):
            # config.json — берём email_mapping
            mapping = obj.get("email_mapping")
            if mapping is None:
                raise ValueError("В JSON не найден словарь 'email_mapping'")
            df = pd.DataFrame([{"name": k, "email": v} for k, v in mapping.items()])
            return df
        df = pd.DataFrame(obj)
    elif ext in ("csv", "txt"):
        text = data.decode("utf-8-sig", errors="replace")
        sep = ";" if text.count(";") > text.count(",") else ","
        df = pd.read_csv(io.StringIO(text), sep=sep)
    else:  # xlsx / xls / ods
        df = pd.read_excel(io.BytesIO(data))

    df.columns = [str(c).strip() for c in df.columns]

    name_col = _find_column(df.columns, REF_NAME_ALIASES)
    email_col = _find_column(df.columns, REF_EMAIL_ALIASES)

    if name_col is None:
        raise ValueError(
            f"Не найдена колонка с названием организации. Колонки файла: {list(df.columns)}. "
            "Ожидаются: «Название» / «Организация», «Email» / «Почта»."
        )

    result = pd.DataFrame()
    result["name"] = df[name_col].fillna("").astype(str).str.strip()
    if email_col is not None:
        result["email"] = df[email_col].fillna("").astype(str).str.strip().str.lower()
    else:
        result["email"] = ""

    contact_col = _find_column(df.columns, REF_CONTACT_ALIASES)
    if contact_col is not None:
        result["contact_person"] = df[contact_col].fillna("").astype(str).str.strip()
    else:
        result["contact_person"] = ""

    # очищаем текстовые "nan" и убираем пустые строки
    for col in ("email", "contact_person"):
        result[col] = result[col].replace({"nan": "", "none": "", "None": ""})
    result = result[result["name"].ne("") & (result["name"].str.lower() != "nan")]
    return result.reset_index(drop=True)


def show_import_reference():
    """Вкладка: Загрузка справочников из файлов Excel/CSV/JSON."""
    st.title("📥 Загрузка справочников")
    st.markdown(
        "Загрузите файл со списком организаций, чтобы массово обновить справочник. "
        "Поддерживаются форматы **Excel (.xlsx/.xls)**, **CSV/TXT** и **JSON** (в т.ч. config.json коллег)."
    )

    with st.expander("ℹ️ Какой формат должен быть у файла", expanded=False):
        st.markdown(
            "Файл должен содержать колонки (названия могут отличаться, скрипт поймёт):\n\n"
            "| Колонка | Примеры названий | Обязательно |\n"
            "|---|---|---|\n"
            "| Название организации | `Название`, `Организация`, `Наименование`, `УО` | ✅ |\n"
            "| Email | `Email`, `Почта`, `E-mail` | ✅ |\n"
            "| Контактное лицо | `Контакт`, `Ответственный` | ❌ |"
        )
        sample = pd.DataFrame({
            "Название организации": ["ООО Управление-1", "ЖК Сервис"],
            "Email": ["uk1@mail.ru", "jkservise@yandex.ru"],
            "Контактное лицо": ["Иванова А.П.", "Петров С.С."],
        })
        st.download_button(
            "⬇️ Скачать образец (Excel)",
            to_excel_bytes(sample),
            file_name="образец_справочника.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    uploaded = st.file_uploader(
        "Выберите файл справочника",
        type=["xlsx", "xls", "csv", "txt", "json", "ods"],
        key="ref_file_uploader",
    )

    parsed_df = None
    if uploaded is not None:
        try:
            parsed_df = parse_reference_file(uploaded)
        except Exception as e:
            st.error(f"❌ Не удалось прочитать файл: {e}")
            parsed_df = None

    if parsed_df is not None:
        if parsed_df.empty:
            st.warning("⚠️ В файле не найдено ни одной строки с названием организации.")
            return

        st.success(f"✅ Файл прочитан: {len(parsed_df)} организаций")

        # подсветка строк с некорректными email
        def _row_style(row):
            color = "#ffcccc" if "@" not in row["email"] else ""
            return [f"background-color: {color}"] * len(row)

        st.dataframe(parsed_df.style.apply(_row_style, axis=1),
                     use_container_width=True, height=min(400, 60 + 35 * len(parsed_df)))

        bad = (~parsed_df["email"].str.contains("@")).sum()
        if bad:
            st.warning(f"⚠️ В {bad} строках(е) указан некорректный email — они будут пропущены.")

        mode_label = st.radio(
            "Режим загрузки",
            ["Дополнить (новые добавить, совпадающие обновить)",
             "Заменить (полностью перезаписать справочник)"],
            index=0,
            horizontal=True,
        )
        mode = "merge" if mode_label.startswith("Дополнить") else "replace"

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📤 Загрузить в справочник", type="primary", use_container_width=True):
                records = parsed_df.to_dict("records")
                with st.spinner("Загружаю..."):
                    stats, errors = config_manager.import_organizations(records, mode=mode)
                # синхронизируем БД и чистим кэш
                init_db()
                get_all_organizations_cached.clear()
                st.session_state["import_ref_result"] = (stats, errors)
                st.rerun()
        with col2:
            if st.button("🧹 Очистить", use_container_width=True):
                st.session_state.pop("ref_file_uploader", None)
                st.rerun()

    result = st.session_state.pop("import_ref_result", None)
    if result:
        stats, errors = result
        st.success(
            f"✅ Загрузка завершена: добавлено {stats['added']}, "
            f"обновлено {stats['updated']}, без изменений {stats['skipped']} "
            f"(всего обработано {stats['total']})"
        )
        if errors:
            with st.expander(f"⚠️ Пропущенные строки ({len(errors)})"):
                for err in errors:
                    st.text(err)


def to_excel_bytes(df):
    """Конвертирует DataFrame в bytes xlsx для кнопки скачивания."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return buf.getvalue()


def show_merge():
    """Вкладка: Объединение дубликатов"""
    st.title("🔀 Объединение дубликатов")
    
    st.markdown("### 🤖 Быстрые действия")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🤖 Объединить автоматически (очевидные дубликаты)", type="primary", use_container_width=True):
            with st.spinner("Объединяю..."):
                merged_count, errors = auto_merge_organizations(threshold=2)
            if merged_count > 0:
                st.success(f"✅ Автоматически объединено: {merged_count} пар")
            if errors:
                st.warning(f"️ Ошибок: {len(errors)}")
                for err in errors[:5]:
                    st.text(f"  • {err}")
            st.rerun()
    
    st.markdown("---")
    st.subheader("🔗 Объединённые организации")
    
    merged_df = get_merged_organizations()
    
    if merged_df.empty:
        st.info("Нет объединённых организаций")
    else:
        st.markdown(f"**Всего объединено:** {len(merged_df)} организаций")
        
        for main_name, group in merged_df.groupby('main_name'):
            with st.expander(f"📁 {main_name}", expanded=False):
                st.markdown(f"**Основная:** {main_name}")
                st.markdown("**Синонимы:**")
                
                for idx, row in group.iterrows():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.text(f"  • {row['synonym_name']}")
                    with col2:
                        if st.button("🔓 Разъединить", key=f"unmerge_{row['synonym_name']}"):
                            success, msg = unmerge_organizations(row['synonym_name'])
                            if success:
                                st.success(f"✅ {row['synonym_name']} разъединена")
                                st.rerun()
                            else:
                                st.error(f"❌ Ошибка: {msg}")
    
    st.markdown("---")
    st.subheader("🔍 Потенциальные дубликаты")
    
    suggestions = get_duplicate_suggestions()
    
    if not suggestions:
        st.success("✅ Дубликатов не найдено!")
    else:
        st.info(f"Найдено {len(suggestions)} пар с похожими названиями")
        
        groups = {}
        for name1, name2, common_words in suggestions:
            key = tuple(sorted(common_words))
            if key not in groups:
                groups[key] = []
            groups[key].append((name1, name2))
        
        for common_words, pairs in groups.items():
            all_names = set()
            for n1, n2 in pairs:
                all_names.add(n1)
                all_names.add(n2)
            
            with st.expander(f"🔸 Общие слова: {', '.join(common_words)} ({len(all_names)} организаций)", expanded=False):
                st.markdown("**Организации в группе:**")
                for name in sorted(all_names):
                    st.text(f"  • {name}")
                
                st.markdown("---")
                st.markdown("**Объединить попарно:**")
                
                for name1, name2 in pairs:
                    col1, col2, col3 = st.columns([2, 2, 2])
                    with col1:
                        if st.button(f"← В '{name1[:30]}...'", key=f"merge_{name1}_{name2}_1"):
                            success, msg = merge_organizations(name2, name1)
                            if success:
                                st.success(f"✅ {name2} → {name1}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
                    with col2:
                        if st.button(f"В '{name2[:30]}...' →", key=f"merge_{name1}_{name2}_2"):
                            success, msg = merge_organizations(name1, name2)
                            if success:
                                st.success(f"✅ {name1} → {name2}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
                    with col3:
                        st.text("")


# ==========================================
# 6. ИНИЦИАЛИЗАЦИЯ (только один раз при старте)
# ==========================================

# Используем session_state, чтобы init_db вызывался только один раз за сессию
if 'db_initialized' not in st.session_state:
    init_db()
    st.session_state.db_initialized = True