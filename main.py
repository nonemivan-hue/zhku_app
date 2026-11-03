import streamlit as st
from pathlib import Path
import sys

# Добавляем папку modules в путь, чтобы Python видел наши скрипты
sys.path.insert(0, str(Path(__file__).parent / "modules"))

# Настройка страницы (широкий макет, заголовок)
st.set_page_config(
    page_title="ЖКУ-Центр",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ИМПОРТ МОДУЛЕЙ ---
# Мы пробуем импортировать каждый скрипт. Если какого-то файла нет, программа не упадет, а просто напишет ошибку.

try:
    import tracker
    TRACKER_AVAILABLE = True
except ImportError as e:
    TRACKER_AVAILABLE = False
    st.error(f"Ошибка импорта tracker: {e}")

try:
    import adler_sort
    ADLER_AVAILABLE = True
except ImportError as e:
    ADLER_AVAILABLE = False

try:
    import mail_sort
    MAIL_AVAILABLE = True
except ImportError as e:
    MAIL_AVAILABLE = False

try:
    import fix_contracts
    FIX_AVAILABLE = True
except ImportError as e:
    FIX_AVAILABLE = False

# --- БОКОВОЕ МЕНЮ ---
st.sidebar.title("🏢 ЖКУ-Центр")
st.sidebar.markdown("---")

menu = st.sidebar.radio(
    "Выберите раздел",
    [
        "📊 Дашборд",
        "📤 Раскладка по УК",
        "📧 Сортировка почты",
        "🔧 Исправление договоров",
        "⚠️ Контроль",
        "📇 Справочник",
        "🔀 Объединение дубликатов",
        "⚙️ Настройки"  # ← Добавлено
    ],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.info("💡 Все пути можно менять в настройках каждого раздела")

# --- ГЛАВНЫЙ КОНТЕНТ (переключение между вкладками) ---
if menu == "📊 Дашборд":
    if TRACKER_AVAILABLE:
        tracker.show_dashboard()
    else:
        st.error("Модуль tracker не загружен")

elif menu == "📤 Раскладка по УК":
    if ADLER_AVAILABLE:
        adler_sort.show_interface()
    else:
        st.error("Модуль adler_sort не загружен")

elif menu == "📧 Сортировка почты":
    if MAIL_AVAILABLE:
        mail_sort.show_interface()
    else:
        st.error("Модуль mail_sort не загружен")

elif menu == "🔧 Исправление договоров":
    if FIX_AVAILABLE:
        fix_contracts.show_interface()
    else:
        st.error("Модуль fix_contracts не загружен")

elif menu == "⚠️ Контроль":
    if TRACKER_AVAILABLE:
        tracker.show_control()
    else:
        st.error("Модуль tracker не загружен")

elif menu == "📇 Справочник":
    if TRACKER_AVAILABLE:
        tracker.show_directory()
    else:
        st.error("Модуль tracker не загружен")

elif menu == "🔀 Объединение дубликатов":
    if TRACKER_AVAILABLE:
        tracker.show_merge()
    else:
        st.error("Модуль tracker не загружен")

elif menu == "⚙️ Настройки":
    try:
        import settings
        settings.show_settings()
    except ImportError as e:
        st.error(f"Модуль settings не загружен: {e}")