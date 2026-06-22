import os
import sqlite3
import io
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# Фикс путей для стабильности в облаке
try:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
except:
    pass

st.set_page_config(page_title="Sniper BI Matrix v4.1", layout="wide")
DB_FILE = "sniper_bi.db"

# --- ИНИЦИАЛИЗАЦИЯ И СТРУКТУРА БАЗЫ ДАННЫХ ---
def init_db(df_columns=None):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # Сначала создаем системную таблицу для проверки
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metrics'")
        table_exists = cursor.fetchone()
        
        if df_columns:
            if table_exists:
                cursor.execute("PRAGMA table_info(metrics)")
                existing_cols = {row[1] for row in cursor.fetchall()}
                if not set(df_columns).issubset(existing_cols):
                    cursor.execute('DROP TABLE metrics')
                    table_exists = False
            
            columns_sql = []
            for col in df_columns:
                if col in ['Дата', 'Артикул продавца', 'Артикул WB', 'Название', 'Предмет', 'Бренд', 'Удаленный товар', 'Источник_ИмяФайла']:
                    columns_sql.append(f'"{col}" TEXT')
                else:
                    columns_sql.append(f'"{col}" REAL DEFAULT 0')
            
            query = f'''
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    {", ".join(columns_sql)}, 
                    UNIQUE("Артикул продавца", "Дата") ON CONFLICT REPLACE
                )
            '''
            cursor.execute(query)
            
        elif not table_exists:
            # Дефолтная структура на случай, если базы вообще нет, чтобы запустить демо-данные
            default_cols = ['Дата', 'Артикул продавца', 'Артикул WB', 'Название', 'Предмет', 'Бренд', 'Показы', 'Заказали товаров, шт', 'Заказали на сумму, ₽']
            columns_sql = [f'"{c}" TEXT' if c in ['Дата', 'Артикул продавца', 'Артикул WB', 'Название', 'Предмет', 'Бренд'] else f'"{c}" REAL DEFAULT 0' for c in default_cols]
            query = f'CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, {", ".join(columns_sql)}, UNIQUE("Артикул продавца", "Дата") ON CONFLICT REPLACE)'
            cursor.execute(query)
            
        conn.commit()

# --- ФУНКЦИЯ ГЕНЕРАЦИИ ТЕСТОВЫХ ДАННЫХ ---
def load_demo_data():
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        count = conn.execute('SELECT COUNT(*) FROM metrics').fetchone()[0]
        if count == 0:
            # Создаем фейковые данные за последние 3 дня для демонстрации матрицы
            demo_rows = [
                {"Дата": "2026-06-19", "Артикул продавца": "h2100030", "Артикул WB": "879308877", "Название": "Рубашка мужская с длинным рукавом", "Предмет": "Рубашки", "Бренд": "Kari", "Показы": 1500, "Заказали товаров, шт": 12, "Заказали на сумму, ₽": 39840},
                {"Дата": "2026-06-19", "Артикул продавца": "h1100050", "Артикул WB": "837332386", "Название": "Шорты мужские спортивные", "Предмет": "Шорты", "Бренд": "Kari", "Показы": 900, "Заказали товаров, шт": 5, "Заказали на сумму, ₽": 9245},
                
                {"Дата": "2026-06-20", "Артикул продавца": "h2100030", "Артикул WB": "879308877", "Название": "Рубашка мужская с длинным рукавом", "Предмет": "Рубашки", "Бренд": "Kari", "Показы": 1800, "Заказали товаров, шт": 19, "Заказали на сумму, ₽": 63080},
                {"Дата": "2026-06-20", "Артикул продавца": "h1100050", "Артикул WB": "837332386", "Название": "Шорты мужские спортивные", "Предмет": "Шорты", "Бренд": "Kari", "Показы": 1200, "Заказали товаров, шт": 2, "Заказали на сумму, ₽": 3698},
                
                {"Дата": "2026-06-21", "Артикул продавца": "h2100030", "Артикул WB": "879308877", "Название": "Рубашка мужская с длинным рукавом", "Предмет": "Рубашки", "Бренд": "Kari", "Показы": 1011, "Заказали товаров, шт": 1, "Заказали на сумму, ₽": 3320},
                {"Дата": "2026-06-21", "Артикул продавца": "h1100050", "Артикул WB": "837332386", "Название": "Шорты мужские спортивные", "Предмет": "Шорты", "Бренд": "Kari", "Показы": 1450, "Заказали товаров, шт": 8, "Заказали на сумму, ₽": 14792}
            ]
            df_demo = pd.DataFrame(demo_rows)
            df_demo['Источник_ИмяФайла'] = 'demo_built_in.xlsx'
            
            cols = [f'"{c}"' for c in df_demo.columns]
            placeholders = ", ".join(["?"] * len(df_demo.columns))
            cursor = conn.cursor()
            for _, row in df_demo.iterrows():
                vals = [row[c] for c in df_demo.columns]
                cursor.execute(f'INSERT OR REPLACE INTO metrics ({", ".join(cols)}) VALUES ({placeholders})', vals)
            conn.commit()

def clean_sku(val):
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s

def standardize_date(date_val):
    s = str(date_val).strip()
    for fmt in ('%d.%m.%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s

def save_dataframe_to_db(df, filename):
    df['Артикул продавца'] = df['Артикул продавца'].apply(clean_sku)
    df['Дата'] = df['Дата'].apply(standardize_date)
    df['Источник_ИмяФайла'] = filename
    
    for col in df.columns:
        if col not in ['Дата', 'Артикул продавца', 'Артикул WB', 'Название', 'Предмет', 'Бренд', 'Удаленный товар', 'Источник_ИмяФайла']:
            val_clean = df[col].astype(str).str.replace('\xa0', '').str.replace(' ', '')
            val_clean = val_clean.str.replace(',', '.')
            val_clean = val_clean.str.replace(r'[^\d\.\-]', '', regex=True)
            df[col] = pd.to_numeric(val_clean, errors='coerce').fillna(0)
            
    init_db(df.columns)
    
    with sqlite3.connect(DB_FILE) as conn:
        cols = [f'"{c}"' for c in df.columns]
        placeholders = ", ".join(["?"] * len(df.columns))
        cursor = conn.cursor()
        for _, row in df.iterrows():
            vals = [row[c] for c in df.columns]
            cursor.execute(f'INSERT OR REPLACE INTO metrics ({", ".join(cols)}) VALUES ({placeholders})', vals)
        conn.commit()

# Автозапуск генератора демо-данных
load_demo_data()

# --- ФРОНТЕНД ---
st.title("📊 Сводная Матрица и Аналитика Ассортимента WB")

st.sidebar.header("📥 Панель аккумуляции данных")
uploaded_file = st.sidebar.file_uploader("Загрузить Excel / CSV отчет за день или период", type=["xlsx", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            uploaded_df = pd.read_csv(uploaded_file, sep=None, engine='python', dtype=str)
        else:
            uploaded_df = pd.read_excel(uploaded_file, engine='openpyxl', dtype=str)
            
        uploaded_df.columns = [col.replace('\ufeff', '').replace('\xa0', ' ').strip() for col in uploaded_df.columns]
        
        if 'Артикул продавца' in uploaded_df.columns and 'Дата' in uploaded_df.columns:
            save_dataframe_to_db(uploaded_df, uploaded_file.name)
            st.sidebar.success(f"Данные успешно вшиты в базу! Строк: {len(uploaded_df)}")
            st.rerun()
        else:
            st.sidebar.error("В файле должны быть колонки 'Артикул продавца' и 'Дата'")
    except Exception as e:
        st.sidebar.error(f"Сбой парсинга: {e}")

if st.sidebar.button("🗑️ Полностью очистить базу данных"):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DROP TABLE IF EXISTS metrics")
        conn.commit()
    st.sidebar.warning("База данных очищена. Страница перезагружается...")
    st.rerun()

# Чтение и рендеринг матриц
with sqlite3.connect(DB_FILE) as conn:
    min_max_dates = conn.execute('SELECT MIN("Дата"), MAX("Дата") FROM metrics').fetchone()

if not min_max_dates or not min_max_dates[0]:
    st.info("👋 Сводный склад пуст. Загрузи первый сшитый отчет в панели слева, чтобы включить BI-матрицу.")
else:
    g_min_date = datetime.strptime(min_max_dates[0], '%Y-%m-%d')
    g_max_date = datetime.strptime(min_max_dates[1], '%Y-%m-%d')

    st.write("### 🎛️ Настройка среза аналитики")
    col_p1, col_p2 = st.columns([1, 1])
    
    with col_p1:
        selected_period = st.date_input(
            "Задайте анализируемый период дат:",
            value=(g_min_date, g_max_date),
            min_value=g_min_date,
            max_value=g_max_date
        )
        
    if isinstance(selected_period, tuple) and len(selected_period) == 2:
        start_date_str = selected_period[0].strftime('%Y-%m-%d')
        end_date_str = selected_period[1].strftime('%Y-%m-%d')
        
        with sqlite3.connect(DB_FILE) as conn:
            period_df = pd.read_sql_query('SELECT * FROM metrics WHERE "Дата" BETWEEN ? AND ?', conn, params=(start_date_str, end_date_str))
            
        ignored_cols = ['id', 'Дата', 'Артикул продавца', 'Артикул WB', 'Название', 'Предмет', 'Бренд', 'Удаленный товар', 'Источник_ИмяФайла']
        numeric_columns = [c for c in period_df.columns if c not in ignored_cols]
        
        with col_p2:
            target_metric = st.selectbox(
                "Выберите метрику для анализа динамики ассортимента:", 
                options=numeric_columns, 
                index=numeric_columns.index('Показы') if 'Показы' in numeric_columns else 0
            )

        st.write("---")
        st.write(f"### 📊 Сводная матрица по метрике: **{target_metric}** (От даты к дате)")
        
        period_df['Дата_Format'] = pd.to_datetime(period_df['Дата']).dt.strftime('%d.%m.%Y')
        
        # Строим сводную кросс-матрицу
        matrix_df = period_df.pivot_table(
            index=['Артикул продавца', 'Название'],
            columns='Дата_Format',
            values=target_metric,
            aggfunc='sum'
        ).fillna(0)
        
        sorted_columns = sorted(matrix_df.columns, key=lambda x: datetime.strptime(x, '%d.%m.%Y'))
        matrix_df = matrix_df[sorted_columns]
        
        if len(sorted_columns) > 1:
            matrix_df['Абс. Динамика (Конец к Началу)'] = matrix_df[sorted_columns[-1]] - matrix_df[sorted_columns[0]]
        
        # НАДЁЖНЫЙ ГРАДИЕНТ ДЛЯ НОВЫХ ВЕРСИЙ PANDAS
        styled_matrix = matrix_df.style.background_gradient(cmap='RdYlGn', axis=1, subset=sorted_columns)
        st.dataframe(styled_matrix, use_container_width=True)
        
        # Экспорт матрицы
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            matrix_df.reset_index().to_excel(writer, index=False, sheet_name='Матрица Динамики')
        
        st.download_button(
            label="📥 Скачать эту сводную матрицу в Excel",
            data=buffer.getvalue(),
            file_name=f"matrix_{target_metric}_{start_date_str}_to_{end_date_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.write("---")
        st.write("### 📈 Интерактивный график: Сравнение позиций на таймлайне")
        
        all_unique_skus = period_df['Артикул продавца'].unique().tolist()
        default_skus_to_plot = all_unique_skus[:5]
        
        selected_skus_plot = st.multiselect(
            "Выберите артикулы продавца для вывода на график:",
            options=all_unique_skus,
            default=default_skus_to_plot
        )
        
        if not selected_skus_plot:
            st.warning("Выберите хотя бы один артикул, чтобы построить график тренда!")
        else:
            fig = go.Figure()
            for sku in selected_skus_plot:
                sku_data = period_df[period_df['Артикул продавца'] == sku].sort_values(by='Дата')
                sku_name = sku_data['Название'].iloc[0] if not sku_data.empty else ''
                
                fig.add_trace(go.Scatter(
                    x=sku_data['Дата_Format'],
                    y=sku_data[target_metric],
                    mode='lines+markers',
                    name=f"SKU: {sku} ({str(sku_name)[:15]}...)",
                    line=dict(width=3),
                    marker=dict(size=8)
                ))
                
            fig.update_layout(
                title=f"Сравнительная динамика по метрике '{target_metric}' за период {start_date_str} - {end_date_str}",
                xaxis_title="Дата",
                yaxis_title=target_metric,
                hovermode="x unified",
                height=550
            )
            st.plotly_chart(fig, use_container_width=True)
