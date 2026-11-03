import streamlit as st
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).parent))
import config_manager

def show_settings():
    st.title("⚙️ Настройки приложения")
    
    config = config_manager.load_config()
    if not config:
        config = config_manager.get_default_config()
    
    paths = config.get("paths", {})
    
    # Инициализируем session_state для путей
    if "setting_root_folder" not in st.session_state:
        st.session_state.setting_root_folder = paths.get("root_folder", r"Z:\ЖКУ")
    if "setting_mail_base" not in st.session_state:
        st.session_state.setting_mail_base = paths.get("mail_base", r"W:\Poste\2026\10")
    if "setting_reference_base" not in st.session_state:
        st.session_state.setting_reference_base = paths.get("reference_base", r"Z:\ЖКУ\Выгрузка 2026\10")
    if "setting_output_base" not in st.session_state:
        st.session_state.setting_output_base = paths.get("output_base", r"W:\Poste\2026\10\ответы жку")
    if "setting_adler_source" not in st.session_state:
        st.session_state.setting_adler_source = paths.get("adler_source", r"D:\выгрузка 2024")
    if "setting_adler_dest" not in st.session_state:
        st.session_state.setting_adler_dest = paths.get("adler_dest", r"D:\_ЖКУ_")
    
    # ==========================================
    # ПУТИ
    # ==========================================
    st.subheader("📂 Пути к папкам")
    st.markdown("Укажите пути к папкам на вашем компьютере")
    
    col1, col2 = st.columns(2)
    with col1:
        root_folder = st.text_input(
            "📊 Папка ЖКУ (для дашборда)",
            value=st.session_state.setting_root_folder,
            key="input_root_folder"
        )
        mail_base = st.text_input(
            "📧 Почтовая папка (источник)",
            value=st.session_state.setting_mail_base,
            key="input_mail_base"
        )
        adler_source = st.text_input(
            "📤 Папка выгрузки (для раскладки)",
            value=st.session_state.setting_adler_source,
            key="input_adler_source_settings"
        )
    
    with col2:
        reference_base = st.text_input(
            "📚 Папка выгрузки (справочник)",
            value=st.session_state.setting_reference_base,
            key="input_reference_base"
        )
        output_base = st.text_input(
            "📁 Папка для результатов",
            value=st.session_state.setting_output_base,
            key="input_output_base"
        )
        adler_dest = st.text_input(
            "📂 Базовая папка назначения",
            value=st.session_state.setting_adler_dest,
            key="input_adler_dest_settings"
        )
    
    # Кнопка сохранения путей
    if st.button("💾 Сохранить пути", type="primary", use_container_width=True):
        # Обновляем session_state
        st.session_state.setting_root_folder = root_folder
        st.session_state.setting_mail_base = mail_base
        st.session_state.setting_reference_base = reference_base
        st.session_state.setting_output_base = output_base
        st.session_state.setting_adler_source = adler_source
        st.session_state.setting_adler_dest = adler_dest
        
        # Сохраняем в config.json
        paths["root_folder"] = root_folder
        paths["mail_base"] = mail_base
        paths["reference_base"] = reference_base
        paths["output_base"] = output_base
        paths["adler_source"] = adler_source
        paths["adler_dest"] = adler_dest
        config["paths"] = paths
        config_manager.save_config(config)
        
        st.success("✅ Все пути сохранены!")
        st.rerun()
    
    # ==========================================
    # СЛОВАРЬ EMAIL
    # ==========================================
    st.subheader("📧 Словарь организаций и email")
    st.markdown("Добавьте организации и их email адреса")
    
    email_mapping = config.get("email_mapping", {})
    
    if email_mapping:
        st.markdown(f"**Текущие записи:** {len(email_mapping)}")
        for org, email in list(email_mapping.items()):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.text(org)
            with col2:
                st.text(email)
            with col3:
                if st.button("🗑️", key=f"del_{org}"):
                    del email_mapping[org]
                    config["email_mapping"] = email_mapping
                    config_manager.save_config(config)
                    st.success(f"✅ Удалено: {org}")
                    st.rerun()
    
    st.markdown("---")
    st.markdown("**Добавить новую организацию:**")
    
    if "new_org_name" not in st.session_state:
        st.session_state.new_org_name = ""
    if "new_org_email" not in st.session_state:
        st.session_state.new_org_email = ""
    
    col1, col2 = st.columns(2)
    with col1:
        new_org = st.text_input(
            "Название организации", 
            value=st.session_state.new_org_name,
            key="input_new_org",
            placeholder="Например: ООО Новая УК"
        )
    with col2:
        new_email = st.text_input(
            "Email", 
            value=st.session_state.new_org_email,
            key="input_new_email",
            placeholder="Например: new-uk@mail.ru"
        )
    
    if st.button("➕ Добавить организацию", type="primary", use_container_width=True):
        if not new_org.strip():
            st.error("❌ Введите название организации")
        elif not new_email.strip():
            st.error("❌ Введите email")
        else:
            if new_org in email_mapping:
                st.warning(f"⚠️ Организация '{new_org}' уже существует в словаре")
            else:
                email_mapping[new_org] = new_email
                config["email_mapping"] = email_mapping
                
                try:
                    config_manager.save_config(config)
                    st.success(f"✅ Организация '{new_org}' добавлена!")
                    st.session_state.new_org_name = ""
                    st.session_state.new_org_email = ""
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Ошибка сохранения: {e}")
    
    # ==========================================
    # СБРОС
    # ==========================================
    st.markdown("---")
    if st.button("🔄 Сбросить к настройкам по умолчанию", use_container_width=True):
        default_config = config_manager.get_default_config()
        config_manager.save_config(default_config)
        
        # Сбрасываем session_state
        for key in list(st.session_state.keys()):
            if key.startswith("setting_"):
                del st.session_state[key]
        
        st.success("✅ Настройки сброшены!")
        st.rerun()
    
    # ==========================================
    # ЭКСПОРТ/ИМПОРТ
    # ==========================================
    st.markdown("---")
    st.subheader("📤 Экспорт и импорт настроек")
    st.markdown("Передайте файл конфигурации коллегам или импортируйте их настройки")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Экспорт настроек:**")
        if st.button("📥 Скачать конфигурацию", use_container_width=True):
            export_file = config_manager.export_config()
            if export_file:
                st.success(f"✅ Файл сохранен: {export_file}")
                st.info("💡 Передайте этот файл коллеге")
    
    with col2:
        st.markdown("**Импорт настроек:**")
        uploaded_file = st.file_uploader("Выберите файл конфигурации", type=["json"])
        if uploaded_file:
            if st.button("📤 Импортировать", use_container_width=True):
                temp_path = Path(__file__).parent.parent / "temp_import.json"
                with open(temp_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                
                try:
                    config_manager.import_config(temp_path)
                    st.success("✅ Настройки импортированы!")
                    st.info("💡 Перезапустите приложение")
                    temp_path.unlink()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Ошибка импорта: {e}")