# Мониторинг позиций - Отдельное приложение
# Версия 1.4 (Final Fix)
# Дата: 13 февраля 2026

import streamlit as st
import pandas as pd
import numpy as np
import ccxt
from statsmodels.tsa.stattools import coint
import statsmodels.api as sm
import time
from datetime import datetime
import plotly.graph_objects as go

# --- КОНСТАНТЫ ---
# Примерный % движения цены при изменении Z-score на 1.0 (для расчета PnL)
# 1.5% - консервативная оценка для альткоинов без плеча
VOLATILITY_FACTOR = 1.5 

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
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 10px;
    }
    [data-testid="stMetricValue"] {
        font-size: 24px;
    }
</style>
""", unsafe_allow_html=True)

# Заголовок
st.markdown('<p class="main-header">📊 Мониторинг Открытых Позиций</p>', unsafe_allow_html=True)
st.caption("Версия 1.4 | Исправлен расчет PnL и добавлены графики")
st.markdown("---")

# Session state
if 'positions' not in st.session_state:
    st.session_state.positions = []

# --- SIDEBAR ---
with st.sidebar:
    st.header("➕ Добавить позицию")
    
    col1, col2 = st.columns(2)
    with col1:
        coin1 = st.text_input("Монета 1 (LONG)", value="TNSR", key="add_coin1")
    with col2:
        coin2 = st.text_input("Монета 2 (SHORT)", value="ME", key="add_coin2")
    
    entry_z = st.number_input(
        "Z-score входа",
        min_value=-10.0,
        max_value=10.0,
        value=-2.3,
        step=0.1,
        help="Значение Z-score, при котором вы открыли сделку"
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
    st.header("⚙️ Настройки")
    
    exchange_name = st.selectbox("Биржа", ['binance', 'bybit', 'okx'], index=2)
    
    auto_refresh = st.checkbox("Автообновление", value=False)
    if auto_refresh:
        refresh_interval = st.slider("Интервал (мин)", 1, 60, 5)
    
    if st.button("🔄 Обновить сейчас", use_container_width=True):
        st.rerun()

# --- ФУНКЦИЯ РАСЧЕТА ---
@st.cache_data(ttl=300)
def calculate_metrics(exchange_name, coin1, coin2):
    """Считает Z-score, возвращает историю для графика"""
    try:
        exchange = getattr(ccxt, exchange_name)()
        c1, c2 = coin1.upper(), coin2.upper()
        
        # Варианты тикеров
        symbol_variants = [
            (f"{c1}/USDT", f"{c2}/USDT"),
            (f"{c1}-USDT", f"{c2}-USDT"),
            (f"{c1}/USDT:USDT", f"{c2}/USDT:USDT"),
        ]
        
        prices1, prices2 = None, None
        
        for sym1, sym2 in symbol_variants:
            try:
                # Берем больше свечей для красивого графика
                ohlcv1 = exchange.fetch_ohlcv(sym1, '4h', limit=300)
                ohlcv2 = exchange.fetch_ohlcv(sym2, '4h', limit=300)
                
                if not ohlcv1 or not ohlcv2: continue

                p1 = [x[4] for x in ohlcv1]
                p2 = [x[4] for x in ohlcv2]
                dates = [datetime.fromtimestamp(x[0]/1000) for x in ohlcv1]
                
                min_len = min(len(p1), len(p2))
                if min_len < 50: continue
                    
                prices1 = np.array(p1[-min_len:])
                prices2 = np.array(p2[-min_len:])
                dates = dates[-min_len:]
                break
            except:
                continue
        
        if prices1 is None: return None
        
        # OLS Hedge Ratio
        x = sm.add_constant(prices2)
        model = sm.OLS(prices1, x)
        results = model.fit()
        hedge_ratio = results.params[1]
        
        # Спред и Z-score (Векторный расчет)
        spread = prices1 - hedge_ratio * prices2
        mean = spread.mean()
        std = spread.std()
        z_score_series = (spread - mean) / std
        
        return {
            'current_z': z_score_series[-1],
            'z_history': z_score_series,
            'dates': dates,
            'price1': prices1[-1],
            'price2': prices2[-1]
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

# --- ГЛАВНЫЙ ЭКРАН ---
if len(st.session_state.positions) == 0:
    st.info("👋 Добавьте позиции через меню слева.")
else:
    st.markdown("### 📊 Статус позиций")
    
    positions_data = []
    
    # 1. Сбор данных
    for i, pos in enumerate(st.session_state.positions):
        if pos['status'] != 'active': continue
        
        data = calculate_metrics(exchange_name, pos['coin1'], pos['coin2'])
        
        if data:
            curr_z = data['current_z']
            entry_z = pos['entry_z']
            
            # --- ЛОГИКА СТАТУСА ---
            # Цель всегда 0 (средняя). 
            # Чем ближе к 0, тем лучше (если идем от входа).
            dist_to_mean = abs(curr_z)
            
            if dist_to_mean < 0.3:
                status = "💰 ЗАКРЫВАТЬ"
                status_color = "green"
            elif dist_to_mean < 1.0:
                status = "⚠️ Близко"
                status_color = "orange"
            elif dist_to_mean > 3.5:
                status = "🚨 ОПАСНО"
                status_color = "red"
            else:
                status = "✅ Держим"
                status_color = "blue"

            # --- ИСПРАВЛЕННАЯ ЛОГИКА ПРИБЫЛИ ---
            # 1. Считаем дельту "пройденного пути" по модулю
            # Если Entry = -2.3, Current = -1.0 -> прошли 1.3 (Прибыль)
            # Если Entry = -2.3, Current = -3.0 -> ушли назад на 0.7 (Убыток)
            z_delta = abs(entry_z) - abs(curr_z)
            
            # 2. Считаем % PnL
            # Используем коэффициент: 1 Z-score ~= 1.5% PnL (VOLATILITY_FACTOR)
            pnl_percent = z_delta * VOLATILITY_FACTOR
            
            # 3. Считаем $ PnL
            pnl_usd = pos['size'] * (pnl_percent / 100)
            
            positions_data.append({
                'id': i,
                'pair': pos['pair'],
                'entry_z': entry_z,
                'curr_z': curr_z,
                'status': status,
                'pnl_pct': pnl_percent,
                'pnl_usd': pnl_usd,
                'data': data # сохраняем для детального view
            })
        else:
             positions_data.append({'id': i, 'pair': pos['pair'], 'error': True})

    # 2. Отрисовка таблицы (Custom)
    if positions_data:
        # Заголовки таблицы
        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 2, 2])
        c1.write("**Пара**")
        c2.write("**Вход Z**")
        c3.write("**Тек. Z**")
        c4.write("**Статус**")
        c5.write("**Прибыль**")
        st.divider()
        
        for p in positions_data:
            if 'error' in p:
                st.error(f"❌ Ошибка данных для {p['pair']}")
                continue
                
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 2, 2])
            c1.write(f"**{p['pair']}**")
            c2.write(f"{p['entry_z']:.2f}")
            c3.write(f"{p['curr_z']:.2f}")
            c4.write(p['status'])
            
            # Цвет прибыли
            pnl_color = "green" if p['pnl_usd'] >= 0 else "red"
            c5.markdown(f":{pnl_color}[**${p['pnl_usd']:.2f} ({p['pnl_pct']:.2f}%)**]")
            st.divider()

    # 3. Детальная информация с графиками
    st.markdown("### 📈 Детальная аналитика")
    
    for p in positions_data:
        if 'error' in p: continue
        
        with st.expander(f"График {p['pair']} | PnL: ${p['pnl_usd']:.2f}", expanded=False):
            data = p['data']
            
            # Построение графика Plotly
            fig = go.Figure()
            
            # Линия Z-score
            fig.add_trace(go.Scatter(
                x=data['dates'], 
                y=data['z_history'],
                mode='lines',
                name='Z-Score',
                line=dict(color='#636efa', width=2)
            ))
            
            # Линии уровней
            fig.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Mean (0)")
            fig.add_hline(y=2, line_dash="dot", line_color="red", opacity=0.5)
            fig.add_hline(y=-2, line_dash="dot", line_color="green", opacity=0.5)
            
            # Линия входа
            fig.add_hline(
                y=p['entry_z'], 
                line_color="orange", 
                line_width=2, 
                annotation_text=f"Вход: {p['entry_z']}",
                annotation_position="bottom right"
            )
            
            fig.update_layout(
                title=f"Z-Score Динамика: {p['pair']}",
                xaxis_title="Время",
                yaxis_title="Z-Score",
                height=400,
                margin=dict(l=20, r=20, t=40, b=20),
                template="plotly_dark"
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Кнопки управления
            col_btn1, col_btn2 = st.columns([1, 4])
            with col_btn1:
                if st.button(f"🗑️ Удалить {p['pair']}", key=f"del_{p['id']}"):
                    st.session_state.positions.pop(p['id'])
                    st.rerun()

# Автообновление
if auto_refresh and len(st.session_state.positions) > 0:
    time.sleep(refresh_interval * 60)
    st.rerun()
