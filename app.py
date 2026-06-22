import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import sqlite3
import json
import os
import io

# Настройка страницы на максимальную ширину экрана
st.set_page_config(
    page_title="WB ERP: Анализ Матрицы и Группировка",
    page_icon="📊",
    layout="wide"
)

# Профессиональный UI
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    h1, h2, h3 { color: #1e1e24; font-family: 'Segoe UI', sans-serif; }
    .stDataFrame { background-color: #ffffff; padding: 10px; border-radius: 8px; }
    div.stButton > button { border-radius: 6px; font-weight: bold; }
    .filter-block { background-color: #ffffff; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

DB_PATH = "wb_analytics.db"

# --- РАБОТА С БАЗОЙ ДАННЫХ SQLITE ---
def get_db_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sku_groups (
            sku TEXT PRIMARY KEY,
            group_name TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def load_all_from_db():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = get_db_connection()
    try:
        df_db = pd.read_sql("SELECT * FROM marketplace_data", conn)
        if not df_db.empty and 'Parsed_Date' in df_db.columns:
            df_db['Parsed_Date'] = pd.to_datetime(df_db['Parsed_Date'])
        return df_db
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

def load_groups_from_db():
    conn = get_db_connection()
    try:
        df_groups = pd.read_sql("SELECT * FROM sku_groups", conn)
        return df_groups
    except Exception:
        return pd.DataFrame(columns=['sku', 'group_name'])
    finally:
        conn.close()

def save_multiple_group_mappings(skus, group_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cleaned_group = group_name.strip()
    
    for sku in skus:
        sku_str = str(sku).strip()
        if not sku_str:
            continue
        if cleaned_group == "Без группы" or not cleaned_group:
            cursor.execute("DELETE FROM sku_groups WHERE sku = ?", (sku_str,))
        else:
            cursor.execute("INSERT OR REPLACE INTO sku_groups (sku, group_name) VALUES (?, ?)", (sku_str, cleaned_group))
    conn.commit()
    conn.close()

def save_and_merge_to_db(uploaded_df):
    if uploaded_df is None or uploaded_df.empty:
        return load_all_from_db()
    df_existing = load_all_from_db()
    if df_existing.empty:
        df_combined = uploaded_df
    else:
        df_combined = pd.concat([df_existing, uploaded_df], ignore_index=True)
    
    df_combined = df_combined.drop_duplicates(subset=['Дата', 'Артикул продавца'], keep='last')
    
    conn = get_db_connection()
    df_to_save = df_combined.copy()
    if 'Parsed_Date' in df_to_save.columns:
        df_to_save['Parsed_Date'] = df_to_save['Parsed_Date'].astype(str)
    df_to_save.to_sql("marketplace_data", conn, if_exists="replace", index=False)
    conn.close()
    
    df_combined['Parsed_Date'] = pd.to_datetime(df_combined['Parsed_Date'])
    return df_combined

if 'milestones' not in st.session_state:
    if os.path.exists('milestones.json'):
        with open('milestones.json', 'r', encoding='utf-8') as f:
            st.session_state.milestones = json.load(f)
    else:
        st.session_state.milestones = []

def save_milestones():
    with open('milestones.json', 'w', encoding='utf-8') as f:
        json.dump(st.session_state.milestones, f, ensure_ascii=False, indent=4)

st.title("🎯 Сводная Аналитическая Матрица WB")

# --- БОКОВАЯ ПАНЕЛЬ ЗАГРУЗКИ ---
st.sidebar.header("📥 Загрузка новых данных")
uploaded_files = st.sidebar.file_uploader(
    "Загрузить отчеты маркетплейса (CSV / XLSX)", 
    type=["csv", "xlsx"], 
    accept_multiple_files=True
)

def parse_files(files):
    all_dfs = []
    for file in files:
        try:
            if file.name.endswith('.csv'):
                df_single = pd.read_csv(file)
            else:
                df_single = pd.read_excel(file)
            all_dfs.append(df_single)
        except Exception as e:
            st.sidebar.error(f"Ошибка чтения {file.name}: {e}")
    if not all_dfs:
        return None
    combined = pd.concat(all_dfs, ignore_index=True)
    combined['Parsed_Date'] = pd.to_datetime(combined['Дата'], format='%d.%m.%Y', errors='coerce')
    combined = combined.dropna(subset=['Parsed_Date'])
    
    metadata = ['Дата', 'Артикул продавца', 'Артикул WB', 'Название', 'Предмет', 'Бренд', 'Удаленный товар', 'Источник_ИмяФайла', 'Parsed_Date']
    for col in combined.columns:
        if col not in metadata and 'время доставки' not in col.lower():
            combined[col] = pd.to_numeric(combined[col].astype(str).str.replace(r'[^0-9.-]', '', regex=True), errors='coerce').fillna(0)
    return combined

df_base = load_all_from_db()

if uploaded_files:
    df_new = parse_files(uploaded_files)
    if df_new is not None:
        df_base = save_and_merge_to_db(df_new)
        st.sidebar.success(f"База данных SQLite обновлена!")

if df_base.empty and os.path.exists("merged_templates_output.xlsx - Sheet1.csv"):
    df_demo = parse_files([open("merged_templates_output.xlsx - Sheet1.csv", "rb")])
    df_base = save_and_merge_to_db(df_demo)

if not df_base.empty:
    metadata_cols = ['Дата', 'Артикул продавца', 'Артикул WB', 'Название', 'Предмет', 'Бренд', 'Удаленный товар', 'Источник_ИмяФайла', 'Parsed_Date']
    all_metrics = [col for col in df_base.columns if col not in metadata_cols]
    
    df_groups_map = load_groups_from_db()
    group_dict = dict(zip(df_groups_map['sku'].astype(str), df_groups_map['group_name']))
    
    st.sidebar.info(f"🗄️ Накоплено дней: {df_base['Parsed_Date'].dt.date.nunique()} | Артикулов: {df_base['Артикул продавца'].nunique()}")
    if st.sidebar.button("🗑️ Стереть всю БД SQLite"):
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        st.rerun()

    # --- ПЕРИОД АНАЛИЗА ---
    st.markdown("### 📅 1. Настройка периода")
    min_date = df_base['Parsed_Date'].min().date()
    max_date = df_base['Parsed_Date'].max().date()
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Начало периода", min_date, min_value=min_date, max_value=max_date)
    with col_d2:
        end_date = st.date_input("Конец периода", max_date, min_value=min_date, max_value=max_date)

    # --- УПРАВЛЕНИЕ МЕТРИКАМИ И СПАРКЛАЙНАМИ ---
    st.markdown("### ⚙️ 2. Выбор выводимых метрик, спарклайнов и LFL расчетов")
    
    if 'metrics_widget' not in st.session_state:
        st.session_state.metrics_widget = ['Показы', 'CTR', 'Переходы в карточку', 'Заказали товаров, шт', 'Заказали на сумму, ₽']

    col_b1, col_b2, _ = st.columns([1, 1, 4])
    if col_b1.button("✅ Выбрать ВСЕ столбцы"):
        st.session_state.metrics_widget = all_metrics
        st.rerun()
    if col_b2.button("❌ Сбросить выбор"):
        st.session_state.metrics_widget = []
        st.rerun()

    col_m_choice, col_spark_choice, col_lfl_choice = st.columns(3)
    with col_m_choice:
        chosen_metrics = st.multiselect("Столбцы метрик в таблице:", options=all_metrics, key="metrics_widget")
    with col_spark_choice:
        sparkline_metrics = st.multiselect("Включить график-спарклайн к полям:", options=chosen_metrics, default=[])
    with col_lfl_choice:
        lfl_modes = st.multiselect(
            "Дополнительные LFL расчеты (относительно конечной даты):",
            options=["День к дню (DoD, %)", "Неделя к неделе (WoW, %)"],
            default=[]
        )

    # --- СБОРКА ДАННЫХ ---
    df_period = df_base[(df_base['Parsed_Date'].dt.date >= start_date) & (df_base['Parsed_Date'].dt.date <= end_date)]
    
    if df_period.empty:
        st.warning("В выбранном диапазоне дат нет данных.")
    else:
        stable_subjects = sorted(df_period['Предмет'].dropna().unique().tolist())
        stable_brands = sorted(df_period['Бренд'].dropna().unique().tolist())
        stable_groups = sorted(list(set(group_dict.values())))

        summary_rows = []
        for sku, group in df_period.groupby('Артикул продавца'):
            group = group.sort_values('Parsed_Date')
            row_start = group.iloc[0]
            row_end = group.iloc[-1]
            
            sku_str = str(sku)
            sku_info = {
                "Артикул продавца": sku_str,
                "Группа": group_dict.get(sku_str, "Без группы"),
                "Название": row_end['Название'],
                "Предмет": row_end['Предмет'],
                "Бренд": row_end['Бренд']
            }
            
            sku_global = df_base[df_base['Артикул продавца'] == sku]
            end_dt = row_end['Parsed_Date']
            yesterday_dt = end_dt - pd.Timedelta(days=1)
            last_week_dt = end_dt - pd.Timedelta(days=7)
            
            def get_historical_value(df_sku, target_date, m_name):
                match = df_sku[df_sku['Parsed_Date'].dt.date == target_date.date()]
                if not match.empty:
                    return float(match.iloc[0][m_name])
                return None

            for metric in chosen_metrics:
                val_start = float(row_start[metric]) if isinstance(row_start[metric], (int, float, np.number)) else 0.0
                val_end = float(row_end[metric]) if isinstance(row_end[metric], (int, float, np.number)) else 0.0
                delta = round(val_end - val_start, 2)
                
                start_label = row_start['Parsed_Date'].strftime('%d.%m')
                end_label = row_end['Parsed_Date'].strftime('%d.%m')
                
                sku_info[f"{metric} (Старт: {start_label})"] = round(val_start, 2)
                
                if metric in sparkline_metrics:
                    sku_info[f"{metric} (Тренд)"] = [round(float(x), 2) for x in group[metric].tolist()]
                    
                sku_info[f"{metric} (Конец: {end_label})"] = round(val_end, 2)
                sku_info[f"{metric} (Динамика)"] = delta
                
                if "День к дню (DoD, %)" in lfl_modes:
                    val_yesterday = get_historical_value(sku_global, yesterday_dt, metric)
                    if val_yesterday is not None and val_yesterday != 0:
                        sku_info[f"{metric} (DoD, %)"] = round(((val_end - val_yesterday) / val_yesterday) * 100, 2)
                    else:
                        sku_info[f"{metric} (DoD, %)"] = 0.0
                        
                if "Неделя к неделе (WoW, %)" in lfl_modes:
                    val_last_week = get_historical_value(sku_global, last_week_dt, metric)
                    if val_last_week is not None and val_last_week != 0:
                        sku_info[f"{metric} (WoW, %)"] = round(((val_end - val_last_week) / val_last_week) * 100, 2)
                    else:
                        sku_info[f"{metric} (WoW, %)"] = 0.0
                
            summary_rows.append(sku_info)
            
        summary_df = pd.DataFrame(summary_rows)

        # --- БЛОК СТАБИЛЬНОЙ ФИЛЬТРАЦИИ И СОРТИРОВКИ ---
        st.markdown("### 🔍 3. Фильтры и обнаружение проблемных товаров")
        
        with st.container():
            st.markdown("<div class='filter-block'>", unsafe_allow_html=True)
            f_c1, f_c2, f_c3 = st.columns(3)
            
            with f_c1:
                filter_group = st.multiselect("Фильтр по Вашим группам:", options=stable_groups, default=[])
            with f_c2:
                filter_subject = st.multiselect("Фильтр по Предмету:", options=stable_subjects, default=[])
            with f_c3:
                filter_brand = st.multiselect("Фильтр по Бренду:", options=stable_brands, default=[])
                
            st.markdown("---")
            col_toggle, col_metric_drop = st.columns([2, 2])
            with col_toggle:
                show_only_falling = st.toggle("🚨 Показать только 'падающий' и проблемный товар", value=False)
            with col_metric_drop:
                falling_metric = st.selectbox("Искать падение по метрике:", options=chosen_metrics if chosen_metrics else ['Показы'], index=0)
            st.markdown("</div>", unsafe_allow_html=True)

        if filter_group:
            summary_df = summary_df[summary_df['Группа'].isin(filter_group)]
        if filter_subject:
            summary_df = summary_df[summary_df['Предмет'].isin(filter_subject)]
        if filter_brand:
            summary_df = summary_df[summary_df['Бренд'].isin(filter_brand)]
            
        if show_only_falling:
            target_delta_col = f"{falling_metric} (Динамика)"
            if target_delta_col in summary_df.columns:
                summary_df = summary_df[summary_df[target_delta_col] < 0]
                summary_df = summary_df.sort_values(by=target_delta_col, ascending=True)

        # --- ОТРИСОВКА СВОДНОЙ ТАБЛИЦЫ ---
        if not summary_df.empty:
            st.markdown(f"### 📋 Результаты сводного анализа матрицы ({len(summary_df)} шт.)")
            
            column_config = {
                "Артикул продавца": st.column_config.TextColumn("Артикул", width="small"),
                "Группа": st.column_config.TextColumn("Группа", width="small"),
                "Название": st.column_config.TextColumn("Название", width="medium"),
                "Предмет": st.column_config.TextColumn("Предмет", width="small"),
                "Бренд": st.column_config.TextColumn("Бренд", width="small")
            }
            
            for metric in sparkline_metrics:
                column_config[f"{metric} (Тренд)"] = st.column_config.LineChartColumn(f"📈 {metric}", width="medium")
                
            for col in summary_df.columns:
                if any(k in col for k in ["Динамика", "Старт:", "Конец:", "DoD", "WoW"]) and "Тренд" not in col:
                    if pd.api.types.is_numeric_dtype(summary_df[col]):
                        short_title = col.replace(" (предыдущий период)", " (пред. пер.)") \
                                         .replace(" (Динамика)", " Δ") \
                                         .replace("День к дню ", "") \
                                         .replace("Неделя к неделе ", "")
                        
                        column_config[col] = st.column_config.NumberColumn(
                            label=short_title, 
                            format="%.2f", 
                            width=100
                        )

            highlight_cols = [c for c in summary_df.columns if any(k in c for k in ["(Динамика)", "DoD, %", "WoW, %"])]
            
            def style_cells(val):
                if isinstance(val, (int, float, np.number)):
                    if val > 0: return 'background-color: #e2f0d9; color: #385723; font-weight: bold;'
                    elif val < 0: return 'background-color: #fce4d6; color: #c65911; font-weight: bold;'
                return ''
                
            # ЖЕСТКИЙ ФИКС СОВМЕСТИМОСТИ ДЛЯ ОБЛАКА И ЛОКАЛКИ
            if hasattr(summary_df.style, 'map'):
                styled_df = summary_df.style.map(style_cells, subset=highlight_cols)
            else:
                styled_df = summary_df.style.applymap(style_cells, subset=highlight_cols)
            
            st.dataframe(styled_df, use_container_width=True, hide_index=True, column_config=column_config)
            
            # ЭКСПОРТ В EXCEL
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                export_df = summary_df.copy()
                spark_cols = [c for c in export_df.columns if " (Тренд)" in c]
                export_df = export_df.drop(columns=spark_cols, errors='ignore')
                export_df.to_excel(writer, index=False, sheet_name='WB_Matrix_Analytics')
                
            st.download_button(
                label="📥 Экспортировать сводный отчет в чистый EXCEL (.xlsx)",
                data=buffer.getvalue(),
                file_name=f"wb_full_matrix_report_{start_date}_to_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Товары по заданным критериям фильтрации не найдены.")

    # --- БЛОК 4: МАССОВОЕ ГРУППИРОВАНИЕ (ВСТАВКА ИЗ EXCEL) ---
    st.markdown("---")
    st.markdown("### 📦 4. Массовое группирование и менеджмент артикулов")
    
    g_col1, g_col2 = st.columns([2, 3])
    with g_col1:
        st.markdown("#### Форма массового добавления в группу")
        with st.form(key="bulk_grouping_form", clear_on_submit=False):
            new_group_name = st.text_input("Название группы (создайте новую или введите существующую):", value="")
            
            st.markdown("**Способ 1: Выберите артикулы вручную (с поиском)**")
            all_db_skus = sorted(df_base['Артикул продавца'].unique().astype(str))
            selected_skus_list = st.multiselect("Кликните или начните вводить артикул:", options=all_db_skus)
            
            st.markdown("**Способ 2: Вставьте список артикулов из Excel (через запятую или в столбик)**")
            pasted_skus_text = st.text_area("Вставьте скопированный столбец или список артикулов:", value="", placeholder="29200250\n19400350\nh1100050")
            
            submit_group = st.form_submit_button("📦 Сохранить группу для всех выбранных артикулов")
            
            if submit_group and new_group_name:
                parsed_pasted_skus = [x.strip() for x in pasted_skus_text.replace(',', ' ').split() if x.strip()]
                final_skus_to_update = list(set(selected_skus_list + parsed_pasted_skus))
                
                if final_skus_to_update:
                    save_multiple_group_mappings(final_skus_to_update, new_group_name)
                    st.success(f"Успешно обработано артикулов: {len(final_skus_to_update)}. Группа '{new_group_name}' сохранена.")
                    st.rerun()
                else:
                    st.error("Вы не выбрали и не вставили ни одного артикула.")
                
    with g_col2:
        st.markdown("#### Текущая структура созданных групп")
        all_current_groups = load_groups_from_db()
        if not all_current_groups.empty:
            st.dataframe(all_current_groups, use_container_width=True, hide_index=True)
        else:
            st.write("Список кастомных групп пуст.")

    # --- БЛОК 5: МАРКЕТИНГОВЫЕ ОТСЕЧКИ И ОБЩИЙ ТАЙМЛАЙН ---
    st.markdown("---")
    st.markdown("### 📍 5. Календарь маркетинговых отсечек и общий таймлайн")
    col_m1, col_m2 = st.columns([1, 2])
    with col_m1:
        st.markdown("#### Добавить событие")
        with st.form(key='new_milestone_form', clear_on_submit=True):
            m_date = st.date_input("Дата отсечки", max_date)
            m_sku = st.selectbox("Применить к артикулу:", ["Все артикулы"] + sorted(df_base['Артикул продавца'].unique().astype(str)), key="milestone_sku_select")
            m_comment = st.text_input("Суть события")
            btn_sub = st.form_submit_button("Записать событие")
            if btn_sub and m_comment:
                st.session_state.milestones.append({"date": m_date.strftime("%Y-%m-%d"), "sku": m_sku, "comment": m_comment})
                save_milestones()
                st.success("Отсечка сохранена!")
                st.rerun()
    with col_m2:
        st.markdown("#### Хроника событий в выбранном периоде")
        if st.session_state.milestones:
            for idx, m in enumerate(st.session_state.milestones):
                m_dt = pd.to_datetime(m['date']).date()
                if start_date <= m_dt <= end_date:
                    c_l, c_r = st.columns([5, 1])
                    c_l.info(f"📅 **{m['date']}** | **{m['sku']}**: {m['comment']}")
                    if c_r.button("🗑️", key=f"del_m_{idx}"):
                        st.session_state.milestones.pop(idx)
                        save_milestones()
                        st.rerun()

    st.markdown("#### Сквозной график для отслеживания эффективности отсечек")
    g_c1, g_c2 = st.columns(2)
    with g_c1:
        graph_skus = st.multiselect("Выберите артикулы для проверки тренда:", options=sorted(df_base['Артикул продавца'].unique().astype(str)), default=[sorted(df_base['Артикул продавца'].unique().astype(str))[0]])
    with g_c2:
        graph_metric = st.selectbox("Выберите метрику:", all_metrics, key="graph_metric_main")

    df_graph = df_period[df_period['Артикул продавца'].astype(str).isin(graph_skus)].sort_values('Parsed_Date')
    if not df_graph.empty:
        fig = px.line(df_graph, x='Parsed_Date', y=graph_metric, color='Артикул продавца', markers=True, template='plotly_white')
        for m in st.session_state.milestones:
            m_dt = pd.to_datetime(m['date']).date()
            if start_date <= m_dt <= end_date and (m['sku'] == "Все артикулы" or m['sku'] in graph_skus):
                fig.add_vline(x=pd.to_datetime(m['date']).timestamp() * 1000, line_dash="dash", line_color="red")
                fig.add_annotation(x=m['date'], y=df_graph[graph_metric].max() * 0.9, text=m['comment'], font=dict(color="red", size=10), bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("База данных пуста. Загрузите файлы в боковую панель.")
