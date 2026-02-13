# Мониторинг позиций - Отдельное приложение
# Версия 1.0
# Дата: 11 февраля 2026

import streamlit as st
import pandas as pd
import numpy as np
import ccxt
from statsmodels.tsa.stattools import coint
import time
from datetime import datetime
import plotly.graph_objects as go

# Настройка страницы
st.set_page_config(
    page_title="Мониторинг Позиций",
    page_icon="📊",
    layout="wide"
)

# CSS стили
st.markdown("""
<style>
    .main-header {
        font-size: 36px;
        font-weight: bold;
        text-align: center;
        padding: 20px;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
</style>
""", unsafe_allow_html=True)

# Заголовок
st.markdown('<p class="main-header">📊 Мониторинг Открытых Позиций</p>', unsafe_allow_html=True)
st.caption("Версия 1.2 | Обновлено: 13 февраля 2026 | Улучшенная обработка ошибок")
st.markdown("---")

# Session state для позиций
if 'positions' not in st.session_state:
    st.session_state.positions = []

# Sidebar - добавление позиций
with st.sidebar:
    st.header("➕ Добавить позицию")
    
    col1, col2 = st.columns(2)
    with col1:
        coin1 = st.text_input("Монета 1 (LONG)", value="BTC", key="add_coin1")
    with col2:
        coin2 = st.text_input("Монета 2 (SHORT)", value="ETH", key="add_coin2")
    
    entry_z = st.number_input(
        "Z-score входа",
        min_value=-5.0,
        max_value=5.0,
        value=-2.3,
        step=0.1
    )
    
    position_size = st.number_input(
        "Размер позиции ($)",
        min_value=10.0,
        max_value=100000.0,
        value=1000.0,
        step=50.0
    )
    
    if st.button("➕ Добавить позицию", use_container_width=True):
        new_position = {
            'pair': f"{coin1}/{coin2}",
            'coin1': coin1,
            'coin2': coin2,
            'entry_z': entry_z,
            'size': position_size,
            'entry_time': datetime.now(),
            'status': 'active'
        }
        st.session_state.positions.append(new_position)
        st.success(f"✅ Добавлена позиция {coin1}/{coin2}")
        st.rerun()
    
    st.markdown("---")
    
    # Настройки
    st.header("⚙️ Настройки")
    
    exchange_name = st.selectbox(
        "Биржа",
        ['binance', 'bybit', 'okx'],
        index=2  # OKX по умолчанию
    )
    
    auto_refresh = st.checkbox("Автообновление", value=False)
    
    if auto_refresh:
        refresh_interval = st.slider(
            "Интервал обновления (мин)",
            min_value=1,
            max_value=60,
            value=5
        )
    
    # Кнопка обновления
    if st.button("🔄 Обновить сейчас", use_container_width=True):
        st.rerun()

# Функция расчета Z-score
@st.cache_data(ttl=300)  # Кеш на 5 минут
def calculate_zscore(exchange_name, coin1, coin2):
    """Рассчитать текущий Z-score для пары"""
    try:
        # Инициализация биржи
        exchange = getattr(ccxt, exchange_name)()
        
        # Пробуем разные варианты символов
        symbol_variants = [
            (f"{coin1}/USDT", f"{coin2}/USDT"),
            (f"{coin1}/USDT:USDT", f"{coin2}/USDT:USDT"),  # Futures
            (f"{coin1.upper()}/USDT", f"{coin2.upper()}/USDT"),
        ]
        
        prices1 = None
        prices2 = None
        
        for sym1, sym2 in symbol_variants:
            try:
                ohlcv1 = exchange.fetch_ohlcv(sym1, '4h', limit=210)  # 35 дней
                ohlcv2 = exchange.fetch_ohlcv(sym2, '4h', limit=210)
                
                prices1 = np.array([x[4] for x in ohlcv1])
                prices2 = np.array([x[4] for x in ohlcv2])
                break
            except:
                continue
        
        if prices1 is None or prices2 is None:
            return None
        
        # Коинтеграция
        score, pvalue, (hedge_ratio,) = coint(prices1, prices2)
        
        # Спред
        spread = prices1 - hedge_ratio * prices2
        
        # Z-score
        z_score = (spread[-1] - spread.mean()) / spread.std()
        
        # Текущие цены
        current_price1 = prices1[-1]
        current_price2 = prices2[-1]
        
        return {
            'z_score': z_score,
            'hedge_ratio': hedge_ratio,
            'pvalue': pvalue,
            'price1': current_price1,
            'price2': current_price2,
            'spread': spread
        }
    except Exception as e:
        st.warning(f"⚠️ Не удалось получить данные для {coin1}/{coin2}: {str(e)}")
        return None

# Главный интерфейс
if len(st.session_state.positions) == 0:
    st.info("""
    📊 **Добро пожаловать в мониторинг позиций!**
    
    Используйте sidebar слева чтобы добавить свои открытые позиции.
    
    **Возможности:**
    - Мониторинг Z-score в реальном времени
    - Автоматические алерты на выход
    - Расчет текущей прибыли/убытка
    - Рекомендации по стоп-лоссу
    - Прогресс к цели
    """)
else:
    # Таблица статуса
    st.markdown("### 📊 Таблица статуса позиций")
    
    positions_data = []
    
    for i, pos in enumerate(st.session_state.positions):
        if pos['status'] != 'active':
            continue
        
        # Рассчитываем Z-score
        result = calculate_zscore(exchange_name, pos['coin1'], pos['coin2'])
        
        if result:
            current_z = result['z_score']
            entry_z = pos['entry_z']
            
            # Определяем статус
            if abs(current_z) < 0.5:
                status = "🎯 ВЫХОДИТЬ!"
            elif abs(current_z) < 1.0:
                status = "⚠️ Близко"
            elif abs(current_z) > 3.5:
                status = "🚨 ОПАСНО!"
            else:
                status = "✅ Держим"
            
            # Расчет прибыли
            if entry_z < 0:  # LONG
                profit_pct = ((abs(entry_z) - abs(current_z)) / abs(entry_z)) * 100
            else:  # SHORT
                profit_pct = ((abs(current_z) - abs(entry_z)) / abs(entry_z)) * 100
            
            profit_usd = pos['size'] * (profit_pct / 100) * 0.7  # Hedge efficiency
            
            positions_data.append({
                'Пара': pos['pair'],
                'Вход Z': round(entry_z, 2),
                'Текущий Z': round(current_z, 2),
                'Статус': status,
                'Прибыль %': round(profit_pct, 2),
                'Прибыль $': round(profit_usd, 2)
            })
        else:
            positions_data.append({
                'Пара': pos['pair'],
                'Вход Z': round(pos['entry_z'], 2),
                'Текущий Z': '❌',
                'Статус': 'Ошибка',
                'Прибыль %': '-',
                'Прибыль $': '-'
            })
    
    # Отображаем таблицу
    if positions_data:
        df = pd.DataFrame(positions_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Детальная информация
    st.markdown("---")
    st.markdown("### 📋 Детальная информация")
    
    for i, pos in enumerate(st.session_state.positions):
        if pos['status'] != 'active':
            continue
        
        with st.expander(f"📊 {pos['pair']}", expanded=False):
            result = calculate_zscore(exchange_name, pos['coin1'], pos['coin2'])
            
            if result:
                current_z = result['z_score']
                entry_z = pos['entry_z']
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Текущий Z", f"{current_z:.2f}")
                    if abs(current_z) < 0.5:
                        st.success("🎯 ВЫХОДИТЬ!")
                
                with col2:
                    if entry_z < 0:
                        profit_pct = ((abs(entry_z) - abs(current_z)) / abs(entry_z)) * 100
                    else:
                        profit_pct = ((abs(current_z) - abs(entry_z)) / abs(entry_z)) * 100
                    
                    profit_usd = pos['size'] * (profit_pct / 100) * 0.7
                    st.metric("Прибыль", f"${profit_usd:.2f}", f"{profit_pct:.2f}%")
                
                with col3:
                    stop_z = entry_z - 1.0 if entry_z < 0 else entry_z + 1.0
                    st.metric("Стоп", f"{stop_z:.2f}")
                
                with col4:
                    progress = 1 - (abs(current_z) / abs(entry_z))
                    progress = max(0, min(1, progress))
                    st.metric("Прогресс", f"{progress*100:.1f}%")
                
                st.progress(progress, f"К цели: {progress*100:.1f}%")
                
                # Кнопки
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    if st.button(f"✅ Закрыть", key=f"close_{i}"):
                        st.session_state.positions[i]['status'] = 'closed'
                        st.rerun()
                with col_a2:
                    if st.button(f"🗑️ Удалить", key=f"remove_{i}"):
                        st.session_state.positions.pop(i)
                        st.rerun()

# Автообновление
if auto_refresh and len(st.session_state.positions) > 0:
    time.sleep(refresh_interval * 60)
    st.rerun()

st.markdown("---")
st.caption("⚠️ Этот инструмент для мониторинга. Не финансовая рекомендация.")
