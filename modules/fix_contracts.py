import streamlit as st
import os
import dbf
import openpyxl
import xlrd
from xlutils.copy import copy
import logging
from datetime import datetime
from pathlib import Path

# ==========================================
# НАСТРОЙКИ ПО УМОЛЧАНИЮ
# ==========================================
DEFAULT_TARGET_FOLDER = r"W:\Poste\2026\10\ответы жку"

# ==========================================
# ФУНКЦИИ ОБРАБОТКИ ФАЙЛОВ
# ==========================================

def process_excel_openpyxl(file_path, log_list):
    """Обрабатывает .xlsx файлы (и .xls, которые на самом деле xlsx). Сохраняет форматирование."""
    try:
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active
        
        headers = [str(cell.value).strip() if cell.value else "" for cell in ws[1]]
        
        total_fixed = 0
        changed = False
        
        for i in range(1, 16):
            sum_col = f'SUM_N{i}'
            dog_col = f'DOGOVOR{i}'
            
            if sum_col in headers and dog_col in headers:
                sum_idx = headers.index(sum_col)
                dog_idx = headers.index(dog_col)
                
                for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                    s_val = row[sum_idx].value
                    d_val = row[dog_idx].value
                    
                    try:
                        s_num = float(s_val) if s_val not in (None, '', ' ') else 0.0
                    except:
                        s_num = 0.0
                    
                    try:
                        d_num = float(d_val) if d_val not in (None, '', ' ') else 0.0
                    except:
                        d_num = 0.0
                    
                    if s_num != 0 and d_num == 0:
                        row[dog_idx].value = 1
                        total_fixed += 1
                        changed = True
        
        if changed:
            wb.save(file_path)
            log_list.append(f"✅ Excel (openpyxl): {os.path.basename(file_path)} - исправлено ячеек: {total_fixed}")
        
        return total_fixed
    except Exception:
        # Если openpyxl не смог открыть — значит это настоящий старый .xls
        return -1

def process_excel_xls(file_path, log_list):
    """Обрабатывает старые .xls файлы через xlrd + xlutils, сохраняя форматирование."""
    try:
        rb = xlrd.open_workbook(file_path, formatting_info=True)
        rs = rb.sheet_by_index(0)
        
        if rs.nrows == 0:
            return 0
        
        headers = [str(rs.cell_value(0, col)).strip() for col in range(rs.ncols)]
        
        wb = copy(rb)
        ws = wb.get_sheet(0)
        
        total_fixed = 0
        changed = False
        
        for i in range(1, 16):
            sum_col = f'SUM_N{i}'
            dog_col = f'DOGOVOR{i}'
            
            if sum_col in headers and dog_col in headers:
                sum_idx = headers.index(sum_col)
                dog_idx = headers.index(dog_col)
                
                for row_idx in range(1, rs.nrows):
                    s_val = rs.cell_value(row_idx, sum_idx)
                    d_val = rs.cell_value(row_idx, dog_idx)
                    
                    try:
                        s_num = float(s_val) if s_val not in (None, '', ' ') else 0.0
                    except:
                        s_num = 0.0
                    
                    try:
                        d_num = float(d_val) if d_val not in (None, '', ' ') else 0.0
                    except:
                        d_num = 0.0
                    
                    if s_num != 0 and d_num == 0:
                        ws.write(row_idx, dog_idx, 1)
                        total_fixed += 1
                        changed = True
        
        if changed:
            wb.save(file_path)
            log_list.append(f"✅ Excel (xlrd/xlwt): {os.path.basename(file_path)} - исправлено ячеек: {total_fixed}")
        
        return total_fixed
    except Exception as e:
        log_list.append(f"❌ Ошибка обработки Excel (xlrd) {file_path}: {e}")
        return 0

def process_excel(file_path, log_list):
    """Сначала пробуем openpyxl, если не вышло — xlrd/xlwt"""
    result = process_excel_openpyxl(file_path, log_list)
    if result != -1:
        return result
    return process_excel_xls(file_path, log_list)

def process_dbf(file_path, log_list):
    """Обрабатывает DBF файлы. Использует with record: для корректной записи."""
    try:
        table = dbf.Table(file_path)
        table.open(mode=dbf.READ_WRITE)
        
        # Очищаем имена полей от пробелов (в DBF они всегда 10 символов)
        table_fields = {f.strip().upper(): f for f in table.field_names}
        
        existing_pairs = []
        for i in range(1, 16):
            sum_col = f'SUM_N{i}'
            dog_col = f'DOGOVOR{i}'
            
            if sum_col.upper() in table_fields and dog_col.upper() in table_fields:
                existing_pairs.append((table_fields[sum_col.upper()], table_fields[dog_col.upper()]))
        
        if not existing_pairs:
            log_list.append(f"⚠️ DBF: В {os.path.basename(file_path)} не найдены пары DOGOVOR/SUM_N. Пропуск.")
            table.close()
            return 0
        
        fixed_count = 0
        
        for record in table:
            for orig_sum, orig_dog in existing_pairs:
                try:
                    s_val = record[orig_sum]
                    d_val = record[orig_dog]
                    
                    if isinstance(s_val, str): s_val = s_val.strip()
                    if isinstance(d_val, str): d_val = d_val.strip()
                    
                    s_num = float(s_val) if s_val not in (None, '') else 0.0
                    d_num = float(d_val) if d_val not in (None, '') else 0.0
                    
                    if s_num != 0 and d_num == 0:
                        # !!! ВАЖНО: блок with record: обязателен для записи в DBF !!!
                        with record:
                            try:
                                record[orig_dog] = 1
                            except Exception:
                                record[orig_dog] = '1'
                        fixed_count += 1
                except Exception:
                    continue
        
        table.close()
        
        if fixed_count > 0:
            log_list.append(f"✅ DBF: {os.path.basename(file_path)} - исправлено ячеек: {fixed_count}")
        
        return fixed_count
    except Exception as e:
        log_list.append(f"❌ Ошибка обработки DBF {file_path}: {e}")
        return 0

def process_directory(directory_path, progress_callback=None, log_list=None):
    """Обрабатывает все файлы в директории"""
    if log_list is None:
        log_list = []
    
    log_list.append(f"=== НАЧАЛО ОБРАБОТКИ ===")
    log_list.append(f"Целевая папка: {directory_path}")
    log_list.append("Проверяем пары колонок: DOGOVOR1..15 и SUM_N1..15")
    
    total_fixed = 0
    files_processed = 0
    
    # Считаем общее количество файлов для прогресс-бара
    all_files = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_ext = os.path.splitext(file)[1].lower()
            if file_ext in ['.xlsx', '.xls', '.dbf']:
                all_files.append(file_path)
    
    total_files = len(all_files)
    
    for idx, file_path in enumerate(all_files):
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in ['.xlsx', '.xls']:
            files_processed += 1
            total_fixed += process_excel(file_path, log_list)
        elif file_ext == '.dbf':
            files_processed += 1
            total_fixed += process_dbf(file_path, log_list)
        
        if progress_callback:
            progress_callback((idx + 1) / total_files)
    
    log_list.append(f"=== ИТОГ ===")
    log_list.append(f"Обработано файлов: {files_processed}")
    log_list.append(f"Всего исправлено ячеек: {total_fixed}")
    
    return files_processed, total_fixed

# ==========================================
# ИНТЕРФЕЙС
# ==========================================

def show_interface():
    """Интерфейс для исправления договоров"""
    st.title("🔧 Исправление договоров")
    st.markdown("""
    Этот инструмент проверяет файлы на наличие ошибок:
    - Если в столбцах **SUM_N1..15** есть суммы (не 0)
    - А в соответствующих столбцах **DOGOVOR1..15** стоит 0 или пусто
    - То автоматически проставляет **1** в столбцы DOGOVOR
    
    **Поддерживаемые форматы:**
    - Excel (.xlsx, .xls)
    - DBF (.dbf)
    """)
    
    # Настройки путей
    st.markdown("### ⚙️ Настройки")
    
    target_folder = st.text_input(
        "Папка с файлами для проверки",
        value=DEFAULT_TARGET_FOLDER,
        help="Укажите путь к папке, где лежат файлы ответов от организаций"
    )
    
    # Проверка пути
    st.markdown("---")
    st.markdown("### 🔍 Проверка пути")
    
    if os.path.exists(target_folder):
        st.success(f"✅ Папка найдена: {target_folder}")
        
        # Считаем количество файлов
        file_count = 0
        for root, dirs, files in os.walk(target_folder):
            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in ['.xlsx', '.xls', '.dbf']:
                    file_count += 1
        
        st.info(f"📁 Найдено файлов для обработки: **{file_count}**")
    else:
        st.error(f"❌ Папка не найдена: {target_folder}")
        st.warning("Укажите правильный путь к папке с файлами")
        return
    
    # Кнопка запуска
    st.markdown("---")
    if st.button("🚀 Начать проверку и исправление", type="primary", use_container_width=True):
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_area = st.empty()
        
        log_list = []
        
        def update_progress(p):
            progress_bar.progress(p)
            status_text.text(f"Обработано {int(p * 100)}%")
        
        status_text.text("Обработка файлов...")
        
        files_processed, total_fixed = process_directory(target_folder, update_progress, log_list)
        
        progress_bar.progress(1.0)
        status_text.text("✅ Готово!")
        
        # Показ результатов
        st.markdown("### 📊 Результаты")
        
        col1, col2 = st.columns(2)
        col1.metric("Обработано файлов", files_processed)
        col2.metric("Исправлено ячеек", total_fixed)
        
        if total_fixed > 0:
            st.success(f"✅ Найдено и исправлено {total_fixed} ошибок в договорах!")
        else:
            st.info("ℹ️ Ошибок не найдено. Все файлы корректны.")
        
        # Логи
        with st.expander("📋 Подробный лог"):
            st.text("\n".join(log_list))