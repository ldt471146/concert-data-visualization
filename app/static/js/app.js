(() => {
    const page = document.body.dataset.page;
    const charts = new Map();
    const storageKeys = {
        favorites: 'pulseAtlasFavorites',
        comparison: 'pulseAtlasComparison',
        preferences: 'pulseAtlasPreferences',
    };
    const concertIndex = new Map();

    const refreshIcons = () => {
        if (window.lucide) window.lucide.createIcons({ attrs: { 'stroke-width': 1.55 } });
    };

    const escapeHTML = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;'
    }[char]));
    const formatNumber = (value) => Number(value || 0).toLocaleString('zh-CN');
    const formatDate = (value) => value ? new Date(value).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }).replace('/', '.') : '--';
    const toast = (message, type = 'success') => {
        const stack = document.querySelector('.flash-stack') || document.body.appendChild(Object.assign(document.createElement('div'), { className: 'flash-stack' }));
        const item = document.createElement('div');
        item.className = `toast toast-${type}`;
        item.textContent = message;
        stack.appendChild(item);
        window.setTimeout(() => item.remove(), 3600);
    };

    const readStorage = (key, fallback) => {
        try {
            const value = JSON.parse(window.localStorage.getItem(key));
            return value ?? fallback;
        } catch (error) {
            return fallback;
        }
    };
    const writeStorage = (key, value) => window.localStorage.setItem(key, JSON.stringify(value));
    const getFavorites = () => readStorage(storageKeys.favorites, []).map(Number).filter(Number.isFinite);
    const getComparison = () => readStorage(storageKeys.comparison, []).filter((item) => item && item.id);
    const getPreferences = () => {
        const saved = readStorage(storageKeys.preferences, {});
        return { city: '全部', budget: '', status: '全部', artist: '全部', ...(saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {}) };
    };
    const hasPreferences = (preferences = getPreferences()) => Boolean(
        (preferences.city && preferences.city !== '全部') || preferences.budget ||
        (preferences.status && preferences.status !== '全部') || (preferences.artist && preferences.artist !== '全部')
    );
    const buildQuery = (values) => new URLSearchParams(Object.entries(values).filter(([, value]) => value && value !== '全部')).toString();

    const observeReveal = () => {
        const nodes = document.querySelectorAll('[data-reveal]');
        if (!('IntersectionObserver' in window)) {
            nodes.forEach((node) => node.classList.add('is-visible'));
            return;
        }
        const observer = new IntersectionObserver((entries, instance) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    instance.unobserve(entry.target);
                }
            });
        }, { threshold: 0.08 });
        nodes.forEach((node) => observer.observe(node));
    };

    const initTilt = () => {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        document.querySelectorAll('.tilt-card').forEach((card) => {
            card.addEventListener('pointermove', (event) => {
                const rect = card.getBoundingClientRect();
                const x = (event.clientX - rect.left) / rect.width - .5;
                const y = (event.clientY - rect.top) / rect.height - .5;
                card.style.transform = `perspective(900px) rotateX(${y * -1.2}deg) rotateY(${x * 1.2}deg)`;
            });
            card.addEventListener('pointerleave', () => { card.style.transform = ''; });
        });
    };

    const initMobileMenu = () => {
        const trigger = document.querySelector('[data-mobile-menu]');
        const rail = document.querySelector('.side-rail');
        if (!trigger || !rail) return;
        trigger.addEventListener('click', () => rail.classList.toggle('is-open'));
        rail.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => rail.classList.remove('is-open')));
    };

    const initAnchors = () => {
        document.querySelectorAll('[data-scroll-target]').forEach((link) => {
            link.addEventListener('click', () => {
                document.querySelectorAll('.rail-link').forEach((item) => item.classList.remove('is-active'));
                link.classList.add('is-active');
            });
        });
    };

    const fetchJSON = async (url, options = {}) => {
        const response = await fetch(url, options);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || '请求失败');
        return payload;
    };

    const chartTheme = {
        text: '#8a98a3', line: 'rgba(216,231,223,.12)', lime: '#dcff58', coral: '#ff835c',
        cyan: '#5ed5c9', panel: '#101923', ink: '#eff7f0'
    };
    const chartText = { color: chartTheme.text, fontFamily: 'Fira Code', fontSize: 10 };
    const chartTooltip = { backgroundColor: chartTheme.panel, borderColor: chartTheme.line, textStyle: { color: chartTheme.ink, fontFamily: 'Fira Code' } };
    const getChart = (id) => {
        const element = document.getElementById(id);
        if (!element || !window.echarts) return null;
        let chart = charts.get(id);
        if (!chart) {
            chart = window.echarts.init(element, null, { renderer: 'canvas' });
            charts.set(id, chart);
        }
        return chart;
    };
    const renderEmptyChart = (id) => {
        const chart = getChart(id);
        if (!chart) return;
        chart.clear();
        chart.setOption({ graphic: { type: 'text', left: 'center', top: 'middle', style: { text: '暂无数据', fill: chartTheme.text, fontFamily: 'Fira Code', fontSize: 12 } } });
    };
    const optionForBars = (labels, values, color = chartTheme.lime, horizontal = false) => horizontal ? {
        animationDuration: 500, grid: { left: 12, right: 28, top: 8, bottom: 12, containLabel: true }, tooltip: { ...chartTooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
        xAxis: { type: 'value', splitLine: { lineStyle: { color: chartTheme.line } }, axisLabel: chartText, axisLine: { show: false } },
        yAxis: { type: 'category', data: labels.slice().reverse(), axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: chartTheme.ink, fontFamily: 'Fira Sans', fontSize: 11 } },
        series: [{ type: 'bar', data: values.slice().reverse(), barWidth: 10, itemStyle: { color }, label: { show: true, position: 'right', color, fontFamily: 'Fira Code', fontSize: 10 } }]
    } : {
        animationDuration: 500, grid: { left: 12, right: 12, top: 18, bottom: 18, containLabel: true }, tooltip: { ...chartTooltip, trigger: 'axis' },
        xAxis: { type: 'category', data: labels, axisTick: { show: false }, axisLine: { lineStyle: { color: chartTheme.line } }, axisLabel: chartText },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: chartTheme.line } }, axisLabel: chartText, axisLine: { show: false } },
        series: [{ type: 'bar', data: values, barWidth: 18, itemStyle: { color }, label: { show: true, position: 'top', color: chartTheme.ink, fontFamily: 'Fira Code', fontSize: 10 } }]
    };

    const renderCharts = (chartsData = {}) => {
        const city = chartsData.city || [];
        const cityChart = getChart('city-chart');
        if (cityChart && city.length) cityChart.setOption(optionForBars(city.map((item) => item.name), city.map((item) => item.value), chartTheme.lime, true), true); else renderEmptyChart('city-chart');
        const sentiment = chartsData.sentiment || [];
        const sentimentChart = getChart('sentiment-chart');
        if (sentimentChart && sentiment.some((item) => item.value)) sentimentChart.setOption({ animationDuration: 700, tooltip: { ...chartTooltip, trigger: 'item', formatter: '{b}<br/>{c} 条 / {d}%' }, series: [{ type: 'pie', radius: ['52%', '76%'], center: ['50%', '52%'], itemStyle: { borderColor: chartTheme.panel, borderWidth: 4 }, label: { show: true, color: chartTheme.ink, fontFamily: 'Fira Sans', fontSize: 11, formatter: '{b}\n{d}%' }, data: sentiment.map((item, index) => ({ name: item.name, value: item.value, itemStyle: { color: [chartTheme.lime, chartTheme.cyan, chartTheme.coral][index] } })) }] }, true); else renderEmptyChart('sentiment-chart');
        const price = chartsData.price || [];
        const priceChart = getChart('price-chart');
        if (priceChart && price.length) priceChart.setOption(optionForBars(price.map((item) => item.name), price.map((item) => item.value), chartTheme.coral), true); else renderEmptyChart('price-chart');
        const trend = chartsData.trend || [];
        const trendChart = getChart('trend-chart');
        if (trendChart && trend.length) trendChart.setOption({ animationDuration: 650, grid: { left: 8, right: 14, top: 14, bottom: 20, containLabel: true }, tooltip: { ...chartTooltip, trigger: 'axis' }, xAxis: { type: 'category', boundaryGap: false, data: trend.map((item) => item.name), axisTick: { show: false }, axisLine: { lineStyle: { color: chartTheme.line } }, axisLabel: chartText }, yAxis: { type: 'value', splitLine: { lineStyle: { color: chartTheme.line } }, axisLabel: chartText, axisLine: { show: false } }, series: [{ type: 'line', smooth: .3, data: trend.map((item) => item.value), symbol: 'circle', symbolSize: 7, lineStyle: { color: chartTheme.coral, width: 2 }, itemStyle: { color: chartTheme.coral, borderColor: chartTheme.panel, borderWidth: 2 }, areaStyle: { color: 'rgba(255,131,92,.1)' } }] }, true); else renderEmptyChart('trend-chart');
        const region = chartsData.region || [];
        const regionChart = getChart('region-chart');
        if (regionChart && region.length) regionChart.setOption(optionForBars(region.map((item) => item.name), region.map((item) => item.value), chartTheme.cyan, true), true); else renderEmptyChart('region-chart');
    };

    const renderKeywords = (items) => {
        const target = document.getElementById('keyword-cloud');
        if (target) target.innerHTML = items.length ? items.map((item) => `<span title="出现 ${escapeHTML(item.value)} 次">${escapeHTML(item.name)}</span>`).join('') : '<div class="empty-state">暂无关键词</div>';
    };
    const saleClass = (status) => status === '售票中' ? 'sale-open' : status === '即将开售' ? 'sale-soon' : status === '已售罄' ? 'sale-sold' : '';

    const renderMap = (payload = {}) => {
        const items = payload.items || [];
        const chart = getChart('map-chart');
        if (!chart || !items.length) return renderEmptyChart('map-chart');
        chart.setOption({ animationDuration: 600, grid: { left: 8, right: 8, top: 8, bottom: 8 }, tooltip: { ...chartTooltip, formatter: (params) => `${escapeHTML(params.data.name)}<br/>${params.data.value[2]} 场` }, xAxis: { type: 'value', min: 85, max: 130, show: false }, yAxis: { type: 'value', min: 18, max: 54, show: false }, series: [{ type: 'scatter', data: items.map((item) => ({ name: item.name, value: [item.longitude, item.latitude, item.value] })), symbolSize: (value) => Math.max(10, Math.min(28, value[2] * 5 + 8)), itemStyle: { color: chartTheme.lime, shadowBlur: 12, shadowColor: 'rgba(220,255,88,.45)' }, label: { show: true, position: 'right', color: chartTheme.ink, fontFamily: 'Fira Sans', fontSize: 10, formatter: '{b}' } }] }, true);
    };
    const renderMonthlyTrend = (payload = {}) => {
        const items = payload.monthly || [];
        const chart = getChart('monthly-trend-chart');
        if (!chart || !items.length) return renderEmptyChart('monthly-trend-chart');
        chart.setOption({ animationDuration: 650, grid: { left: 8, right: 12, top: 14, bottom: 20, containLabel: true }, tooltip: { ...chartTooltip, trigger: 'axis' }, legend: { top: 0, right: 0, textStyle: chartText, data: ['演出', '评论'] }, xAxis: { type: 'category', boundaryGap: false, data: items.map((item) => item.period), axisLabel: chartText, axisLine: { lineStyle: { color: chartTheme.line } } }, yAxis: { type: 'value', axisLabel: chartText, splitLine: { lineStyle: { color: chartTheme.line } }, axisLine: { show: false } }, series: [{ name: '演出', type: 'line', smooth: .25, data: items.map((item) => item.concerts), lineStyle: { color: chartTheme.lime }, itemStyle: { color: chartTheme.lime } }, { name: '评论', type: 'line', smooth: .25, data: items.map((item) => item.comments), lineStyle: { color: chartTheme.cyan }, itemStyle: { color: chartTheme.cyan } }] }, true);
    };
const calendarState = { year: new Date().getFullYear(), month: new Date().getMonth() + 1, selected: null };
    const calendarHeatClass = (count) => {
        if (!count) return 'cal-heat-null';
        if (count <= 3) return 'cal-heat-low';
        if (count <= 10) return 'cal-heat-mid';
        return 'cal-heat-high';
    };
    const renderCalendar = (payload = {}) => {
        const target = document.getElementById('calendar-grid');
        if (!target) return;
        const items = (payload.items || []).filter((item) => item && (item.concerts != null));
        const byDate = new Map(items.map((item) => [String(item.date || '').slice(0, 10), { count: Number(item.concerts) || 0, detail: item }]));
        const { year, month } = calendarState;
        const first = new Date(year, month - 1, 1);
        const daysInMonth = new Date(year, month, 0).getDate();
        const startWeekday = (first.getDay() + 6) % 7; // 周一=0
        const cells = [];
        for (let i = 0; i < startWeekday; i += 1) cells.push('<span class="cal-cell cal-cell-empty"></span>');
        for (let day = 1; day <= daysInMonth; day += 1) {
            const key = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const entry = byDate.get(key);
            const count = entry ? entry.count : 0;
            const active = calendarState.selected === key;
            cells.push(`<button type="button" class="cal-cell cal-day ${calendarHeatClass(count)}${active ? ' is-selected' : ''}" data-cal-date="${key}" title="${key}${count ? `：${count} 场` : ''}" aria-label="${key}${count ? `，${count} 场` : ''}"><strong>${day}</strong><span>${count ? `${formatNumber(count)} 场` : ''}</span></button>`);
        }
        const monthTitle = `${year} 年 ${month} 月`;
        const detail = calendarState.selected ? byDate.get(calendarState.selected) : null;
        const detailHtml = detail && detail.count
            ? `<section class="cal-detail"><h4>${escapeHTML(calendarState.selected)} · ${formatNumber(detail.count)} 场</h4>${detail.detail.cities && detail.detail.cities.length ? `<p>${escapeHTML(detail.detail.cities.join('、'))}</p>` : ''}${detail.detail.comments ? `<p>${formatNumber(detail.detail.comments)} 条评论</p>` : ''}</section>`
            : '';
        target.innerHTML = `<div class="cal-toolbar"><span class="cal-title">${monthTitle}</span><div class="cal-nav"><button type="button" class="cal-nav-btn" data-cal-prev aria-label="上一月"><i data-lucide="chevron-left"></i></button><button type="button" class="cal-nav-btn" data-cal-today aria-label="回到本月">本月</button><button type="button" class="cal-nav-btn" data-cal-next aria-label="下一月"><i data-lucide="chevron-right"></i></button></div></div><div class="cal-weekdays"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div><div class="cal-grid">${cells.join('')}</div>${detailHtml}`;
        target.querySelectorAll('[data-cal-date]').forEach((node) => node.addEventListener('click', (event) => {
            calendarState.selected = node.dataset.calDate === calendarState.selected ? null : node.dataset.calDate;
            renderCalendar(payload);
        }));
        target.querySelectorAll('[data-cal-prev]').forEach((node) => node.addEventListener('click', () => {
            calendarState.month -= 1;
            if (calendarState.month < 1) { calendarState.month = 12; calendarState.year -= 1; }
            calendarState.selected = null;
            renderCalendar(payload);
        }));
        target.querySelectorAll('[data-cal-next]').forEach((node) => node.addEventListener('click', () => {
            calendarState.month += 1;
            if (calendarState.month > 12) { calendarState.month = 1; calendarState.year += 1; }
            calendarState.selected = null;
            renderCalendar(payload);
        }));
        target.querySelectorAll('[data-cal-today]').forEach((node) => node.addEventListener('click', () => {
            const now = new Date();
            calendarState.year = now.getFullYear();
            calendarState.month = now.getMonth() + 1;
            calendarState.selected = null;
            renderCalendar(payload);
        }));
        if (window.lucide) window.lucide.createIcons();
    };
    const renderPriceAnalysis = (payload = {}) => {
        const items = payload.ranges || [];
        const chart = getChart('price-analysis-chart');
        if (!chart || !items.length) return renderEmptyChart('price-analysis-chart');
        chart.setOption(optionForBars(items.map((item) => item.range), items.map((item) => item.concerts), chartTheme.coral), true);
    };
    const renderTopics = (payload = {}) => {
        const items = (payload.items || []).filter((item) => item.comments);
        const chart = getChart('topics-chart');
        if (!chart || !items.length) return renderEmptyChart('topics-chart');
        chart.setOption(optionForBars(items.map((item) => item.topic), items.map((item) => item.comments), chartTheme.cyan, true), true);
    };
    const renderArtists = (payload = {}) => {
        const items = (payload.items || []).filter((item) => item.heat > 0).slice(0, 10);
        const chart = getChart('artists-chart');
        if (!chart || !items.length) return renderEmptyChart('artists-chart');
        const labels = items.map((item) => (item.artist.length > 8 ? `${item.artist.slice(0, 8)}…` : item.artist)).reverse();
        const values = items.map((item) => item.heat).reverse();
        const counts = items.map((item) => `${item.concerts} 场 / ${formatNumber(item.comments)} 评`).reverse();
        chart.setOption({ animationDuration: 600, grid: { left: 12, right: 30, top: 8, bottom: 12, containLabel: true }, tooltip: { ...chartTooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (params) => `${escapeHTML(params[0]?.name || '')}<br/>热度 ${params[0]?.value || 0}<br/>${counts[params[0]?.dataIndex] || ''}` }, xAxis: { type: 'value', splitLine: { lineStyle: { color: chartTheme.line } }, axisLabel: chartText, axisLine: { show: false } }, yAxis: { type: 'category', data: labels, axisLabel: { color: chartTheme.ink, fontFamily: 'Fira Sans', fontSize: 10 }, axisTick: { show: false }, axisLine: { show: false } }, series: [{ type: 'bar', data: values, barWidth: 10, itemStyle: { color: chartTheme.lime }, label: { show: true, position: 'right', color: chartTheme.lime, fontFamily: 'Fira Code', fontSize: 10 } }] }, true);
    };
    const renderCityPrices = (payload = {}) => {
        const items = (payload.cities || []).slice().sort((a, b) => (b.average_min_price || 0) - (a.average_min_price || 0)).slice(0, 12);
        const chart = getChart('city-price-chart');
        if (!chart || !items.length) return renderEmptyChart('city-price-chart');
        chart.setOption({ animationDuration: 600, grid: { left: 12, right: 36, top: 8, bottom: 12, containLabel: true }, tooltip: { ...chartTooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (params) => `${escapeHTML(params[0]?.name || '')}<br/>均价 ¥${params[0]?.value || 0}` }, xAxis: { type: 'value', splitLine: { lineStyle: { color: chartTheme.line } }, axisLabel: chartText, axisLine: { show: false } }, yAxis: { type: 'category', data: items.map((item) => item.city).reverse(), axisLabel: { color: chartTheme.ink, fontFamily: 'Fira Sans', fontSize: 10 }, axisTick: { show: false }, axisLine: { show: false } }, series: [{ type: 'bar', data: items.map((item) => item.average_min_price || 0).reverse(), barWidth: 10, itemStyle: { color: chartTheme.coral }, label: { show: true, position: 'right', color: chartTheme.coral, fontFamily: 'Fira Code', fontSize: 10, formatter: (p) => `¥${p.value}` } }] }, true);
    };
    const renderEngagement = (payload = {}) => {
        const items = payload.items || [];
        const chart = getChart('engagement-chart');
        if (!chart || !items.length) return renderEmptyChart('engagement-chart');
        const data = items.map((item) => ({ name: item.concert_name || `场次 ${item.concert_id}`, value: item.likes || 0, comments: item.comments || 0, city: item.city || '' }));
        chart.setOption({ animationDuration: 600, color: [chartTheme.cyan], tooltip: { ...chartTooltip, trigger: 'item', formatter: (params) => `${escapeHTML(params.name)}<br/>点赞 ${formatNumber(params.value)}<br/>评论 ${params.data.comments} 条` }, xAxis: { type: 'category', data: data.map((item) => (item.name.length > 10 ? `${item.name.slice(0, 10)}…` : item.name)).reverse(), axisLabel: { ...chartText, rotate: 30, fontSize: 9 }, axisLine: { lineStyle: { color: chartTheme.line } } }, yAxis: { type: 'value', splitLine: { lineStyle: { color: chartTheme.line } }, axisLabel: chartText, axisLine: { show: false } }, series: [{ type: 'bar', data: data.map((item) => item.value).reverse(), barWidth: 12, itemStyle: { color: chartTheme.cyan, borderRadius: [3, 3, 0, 0] }, label: { show: true, position: 'top', color: chartTheme.cyan, fontFamily: 'Fira Code', fontSize: 9, formatter: (p) => formatNumber(p.value) } }] }, true);
    };
    const renderSources = (payload = {}) => {
        const target = document.getElementById('sources-list');
        if (!target) return;
        const items = (payload.items || []).filter((item) => item.concerts > 0);
        target.innerHTML = items.length ? items.map((item) => `<article class="source-item"><span class="source-name">${escapeHTML(item.source)}</span><span class="source-count">${formatNumber(item.concerts)} 场</span><span class="source-meta">覆盖 ${formatNumber(item.artists)} 位艺人 / ${formatNumber(item.cities)} 个城市</span></article>`).join('') : '<div class="empty-state">暂无来源数据</div>';
    };
    const renderExtendedAnalytics = (payloads) => {
        renderMap(payloads[0]);
        renderMonthlyTrend(payloads[1]);
        renderCalendar(payloads[2]);
        renderPriceAnalysis(payloads[3]);
        renderTopics(payloads[4]);
        renderArtists(payloads[5]);
        renderSources(payloads[6]);
        renderCityPrices(payloads[3]);
        renderEngagement(payloads[7]);
    };

    const renderFilters = (meta, current) => {
        const options = [['filter-category', meta.categories], ['filter-artist', meta.artists], ['filter-city', meta.cities], ['filter-status', meta.statuses]];
        options.forEach(([id, values]) => {
            const select = document.getElementById(id);
            if (!select) return;
            const selected = current[select.name] || '全部';
            select.innerHTML = '<option value="全部">全部</option>' + (values || []).map((value) => `<option value="${escapeHTML(value)}">${escapeHTML(value)}</option>`).join('');
            select.value = selected;
        });
        [['preference-city', meta.cities], ['preference-status', meta.statuses], ['preference-artist', meta.artists]].forEach(([id, values]) => {
            const select = document.getElementById(id);
            if (!select) return;
            const preference = getPreferences();
            select.innerHTML = '<option value="全部">全部</option>' + (values || []).map((value) => `<option value="${escapeHTML(value)}">${escapeHTML(value)}</option>`).join('');
            select.value = preference[select.name] || '全部';
        });
        const budget = document.getElementById('preference-budget');
        if (budget) budget.value = getPreferences().budget || '';
    };

    const renderConcerts = (items) => {
        const target = document.getElementById('concert-list');
        if (!target) return;
        concertIndex.clear();
        items.forEach((item) => concertIndex.set(Number(item.id), item));
        const favorites = getFavorites();
        const comparison = getComparison();
        target.innerHTML = items.length ? items.slice(0, 8).map((item) => {
            const id = Number(item.id);
            const favorite = favorites.includes(id);
            const compared = comparison.some((entry) => Number(entry.id) === id);
            return `<article class="schedule-item"><div class="schedule-date">${escapeHTML(item.show_date)}<small>${escapeHTML(item.show_weekday)}</small></div><div class="schedule-main"><h3>${escapeHTML(item.concert_name)}</h3><p><i data-lucide="map-pin"></i>${escapeHTML(item.city)} · ${escapeHTML(item.venue)}</p><span class="sale-status ${saleClass(item.sale_status)}">${escapeHTML(item.sale_status)}</span></div><div class="schedule-price">¥${formatNumber(item.min_price)}<small>起 / ${formatNumber(item.comment_count)} 评论</small></div><div class="schedule-actions"><button class="table-action concert-action ${favorite ? 'is-active' : ''}" type="button" data-concert-action="favorite" data-concert-id="${id}" title="${favorite ? '取消收藏' : '收藏这场演出'}" aria-label="${favorite ? '取消收藏' : '收藏这场演出'}"><i data-lucide="${favorite ? 'star' : 'star'}"></i></button><button class="table-action concert-action ${compared ? 'is-active' : ''}" type="button" data-concert-action="comparison" data-concert-id="${id}" title="${compared ? '移出对比' : '加入对比'}" aria-label="${compared ? '移出对比' : '加入对比'}"><i data-lucide="${compared ? 'check' : 'plus'}"></i></button></div></article>`;
        }).join('') : '<div class="empty-state">当前筛选没有场次</div>';
        refreshIcons();
        renderFavorites();
        renderComparison();
        renderReminders(items);
    };
    const renderReminders = (items) => {
        const target = document.getElementById('reminder-list');
        if (!target) return;
        const now = new Date();
        const limit = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
        const upcoming = items.filter((item) => {
            const date = new Date(item.show_time);
            return item.sale_status === '即将开售' || (date >= now && date <= limit);
        }).slice(0, 8);
        target.innerHTML = upcoming.length ? upcoming.map((item) => `<article class="reminder-item"><div><strong>${escapeHTML(item.concert_name)}</strong><span>${escapeHTML(item.city)} · ${escapeHTML(item.show_date)}</span></div><span class="sale-status ${saleClass(item.sale_status)}">${escapeHTML(item.sale_status || '临近演出')}</span></article>`).join('') : '<div class="empty-state">暂无临近提醒</div>';
    };
    const renderFavorites = () => {
        const count = document.getElementById('favorite-count');
        const target = document.getElementById('favorite-list');
        const favorites = getFavorites();
        const items = favorites.map((id) => concertIndex.get(id)).filter(Boolean);
        if (count) count.textContent = formatNumber(favorites.length);
        if (!target) return;
        target.innerHTML = items.length ? items.map((item) => `<button class="favorite-chip" type="button" data-favorite-remove="${Number(item.id)}" title="取消收藏"><span>${escapeHTML(item.concert_name)}</span><i data-lucide="x"></i></button>`).join('') : '<span>暂无当前场次收藏</span>';
        refreshIcons();
    };
    const renderComparison = () => {
        const target = document.getElementById('comparison-list');
        if (!target) return;
        const items = getComparison();
        if (items.length < 2) {
            target.innerHTML = '<div class="empty-state">从场次列表加入 2 至 3 场后开始对比</div>';
            return;
        }
        const rows = [['艺人', (item) => item.artist_name], ['城市', (item) => item.city], ['演出时间', (item) => item.show_date], ['最低票价', (item) => `¥${formatNumber(item.min_price)}`], ['售票状态', (item) => item.sale_status], ['评论数', (item) => formatNumber(item.comment_count)]];
        target.innerHTML = `<div class="comparison-table-wrap"><table class="comparison-table"><thead><tr><th>项目</th>${items.map((item) => `<th>${escapeHTML(item.concert_name)}<button class="table-action" type="button" data-comparison-remove="${Number(item.id)}" aria-label="移除 ${escapeHTML(item.concert_name)}" title="移除对比"><i data-lucide="x"></i></button></th>`).join('')}</tr></thead><tbody>${rows.map(([label, getter]) => `<tr><th>${label}</th>${items.map((item) => `<td>${escapeHTML(getter(item))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
        refreshIcons();
    };
    const updateFavorite = (id) => {
        const favorites = getFavorites();
        const next = favorites.includes(id) ? favorites.filter((value) => value !== id) : [...favorites, id];
        writeStorage(storageKeys.favorites, next);
        renderConcerts([...concertIndex.values()]);
        toast(next.includes(id) ? '已收藏这场演出' : '已取消收藏');
    };
    const updateComparison = (id) => {
        const current = getComparison();
        const exists = current.some((item) => Number(item.id) === id);
        if (exists) writeStorage(storageKeys.comparison, current.filter((item) => Number(item.id) !== id));
        else {
            if (current.length >= 3) return toast('对比最多保留 3 场', 'error');
            const item = concertIndex.get(id);
            if (item) writeStorage(storageKeys.comparison, [...current, item]);
        }
        renderConcerts([...concertIndex.values()]);
        toast(exists ? '已移出对比' : '已加入对比');
    };

    const renderComments = (items) => {
        const target = document.getElementById('comment-list');
        if (target) target.innerHTML = items.length ? items.map((item) => `<article class="comment-item"><p>${escapeHTML(item.comment_text)}</p><div class="comment-meta"><span>${escapeHTML(item.user_region)} / ${formatDate(item.comment_time)}</span><span class="comment-score">${item.sentiment_score ? Math.round(item.sentiment_score * 100) : '--'} 分</span></div></article>`).join('') : '<div class="empty-state">暂无评论样本</div>';
    };
    const renderRecommendations = (items) => {
        const target = document.getElementById('recommend-list');
        if (!target) return;
        const preferenceNote = hasPreferences() ? '；符合你的偏好' : '';
        target.innerHTML = items.length ? items.map((item, index) => `<article class="recommend-card"><div class="recommend-rank"><span>第 ${index + 1} 项</span><strong class="recommend-score">${escapeHTML(item.score)}</strong></div><div><h3>${escapeHTML(item.concert_name)}</h3><p>${escapeHTML(item.reason || '')}${preferenceNote}</p></div><div class="recommend-meta"><span>${escapeHTML(item.city)} · ${escapeHTML(item.show_date)}</span><strong>¥${formatNumber(item.min_price)}</strong></div></article>`).join('') : '<div class="empty-state">暂无推荐结果</div>';
    };

    const loadDashboard = async (query = '') => {
        const stage = document.querySelector('.main-stage');
        stage?.classList.add('is-loading');
        const names = ['map', 'trend', 'calendar', 'prices', 'topics', 'artists', 'sources', 'engagement'];
        try {
            const overviewPromise = fetchJSON(`/api/overview${query ? `?${query}` : ''}`);
            const analyticsPromise = Promise.all(names.map((name) => fetchJSON(`/api/analytics/${name}${query ? `?${query}` : ''}`).catch((error) => ({ error }))));
            const [payload, analytics] = await Promise.all([overviewPromise, analyticsPromise]);
            const metrics = payload.metrics || {};
            ['concerts', 'comments', 'cities', 'sentiment'].forEach((key) => { const node = document.getElementById(`metric-${key}`); if (node) node.textContent = formatNumber(metrics[key]); });
            const hero = document.getElementById('hero-index');
            if (hero) hero.textContent = formatNumber(metrics.sentiment);
            const updated = document.getElementById('last-updated');
            if (updated) updated.textContent = metrics.last_updated || '暂无';
            renderFilters(payload.meta || {}, payload.meta?.filters || {});
            renderCharts(payload.charts || {});
            renderKeywords(payload.charts?.keywords || []);
            renderConcerts(payload.concerts || []);
            renderComments(payload.comments || []);
            renderRecommendations(payload.recommendations || []);
            renderExtendedAnalytics(analytics.map((item) => item.error ? {} : item));
            if (analytics.some((item) => item.error)) toast('部分分析数据暂时不可用', 'error');
            refreshIcons();
        } catch (error) {
            toast(error.message, 'error');
        } finally {
            stage?.classList.remove('is-loading');
        }
    };

    const initDashboard = () => {
        const form = document.getElementById('filter-form');
        const buildFilterQuery = () => buildQuery(Object.fromEntries(new FormData(form).entries()));
        const preferences = getPreferences();
        form?.addEventListener('submit', (event) => { event.preventDefault(); loadDashboard(buildFilterQuery()); });
        document.querySelector('[data-reset-filters]')?.addEventListener('click', () => { form.reset(); loadDashboard(); });
        document.querySelector('[data-refresh]')?.addEventListener('click', () => loadDashboard(buildFilterQuery()));
        document.getElementById('concert-list')?.addEventListener('click', (event) => {
            const button = event.target.closest('[data-concert-action]');
            if (!button) return;
            const id = Number(button.dataset.concertId);
            if (button.dataset.concertAction === 'favorite') updateFavorite(id); else updateComparison(id);
        });
        document.getElementById('favorite-list')?.addEventListener('click', (event) => {
            const button = event.target.closest('[data-favorite-remove]');
            if (button) updateFavorite(Number(button.dataset.favoriteRemove));
        });
        document.getElementById('comparison-list')?.addEventListener('click', (event) => {
            const button = event.target.closest('[data-comparison-remove]');
            if (!button) return;
            writeStorage(storageKeys.comparison, getComparison().filter((item) => Number(item.id) !== Number(button.dataset.comparisonRemove)));
            renderComparison();
            renderConcerts([...concertIndex.values()]);
        });
        document.querySelector('[data-clear-comparison]')?.addEventListener('click', () => { writeStorage(storageKeys.comparison, []); renderComparison(); renderConcerts([...concertIndex.values()]); });
        document.getElementById('preference-form')?.addEventListener('submit', (event) => {
            event.preventDefault();
            const values = Object.fromEntries(new FormData(event.currentTarget).entries());
            writeStorage(storageKeys.preferences, values);
            toast('偏好已保存');
            loadDashboard(buildQuery({ city: values.city, max_price: values.budget, status: values.status, artist: values.artist }));
        });
        document.querySelector('[data-clear-preferences], #clear-preferences')?.addEventListener('click', () => {
            writeStorage(storageKeys.preferences, { city: '全部', budget: '', status: '全部', artist: '全部' });
            const preferenceForm = document.getElementById('preference-form');
            preferenceForm?.reset();
            toast('偏好已清除');
            loadDashboard();
        });
        window.addEventListener('resize', () => charts.forEach((chart) => chart.resize()));
        initMobileMenu();
        initAnchors();
        loadDashboard(buildQuery({ city: preferences.city, max_price: preferences.budget, status: preferences.status, artist: preferences.artist }));
    };

    const renderImportReport = (report) => {
        const target = document.getElementById('import-report');
        if (!target) return;
        if (!report || typeof report !== 'object') {
            target.innerHTML = '<div class="empty-state">暂无预览报告</div>';
            return;
        }
        const errors = report.errors || [];
        const preview = report.preview || [];
        target.innerHTML = `<div class="report-summary"><span>文件：${escapeHTML(report.filename || '未命名')}</span><span>类型：${escapeHTML(report.kind || '未知')}</span><span>总行数：${formatNumber(report.total_rows ?? report.input_count)}</span><span class="${report.valid === false || errors.length ? 'report-invalid' : 'report-valid'}">${report.valid === false || errors.length ? `发现 ${errors.length} 项问题` : '校验通过'}</span></div>${errors.length ? `<ul class="report-errors">${errors.map((item) => `<li>第 ${escapeHTML(item.row)} 行 / ${escapeHTML(item.field)}：${escapeHTML(item.message || item.code)}</li>`).join('')}</ul>` : ''}${preview.length ? `<div class="report-preview"><table><thead><tr>${Object.keys(preview[0]).map((key) => `<th>${escapeHTML(key)}</th>`).join('')}</tr></thead><tbody>${preview.slice(0, 5).map((row) => `<tr>${Object.values(row).map((value) => `<td>${escapeHTML(value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : ''}`;
    };
    const renderJobDetail = (job) => {
        const target = document.getElementById('job-detail');
        if (!target) return;
        target.hidden = false;
        target.innerHTML = job ? `<div class="job-detail-head"><strong>任务 #${escapeHTML(job.id)}</strong><button class="table-action" type="button" data-close-job-detail aria-label="关闭任务详情">关闭</button></div><dl>${[['任务', job.job_type], ['状态', job.status], ['输入', job.input_count], ['成功', job.success_count], ['异常', job.failed_count], ['启动时间', job.started_at], ['完成时间', job.finished_at || '未完成'], ['结果', job.message]].map(([key, value]) => `<div><dt>${key}</dt><dd>${escapeHTML(value)}</dd></div>`).join('')}</dl>` : '<div class="empty-state">暂无任务详情</div>';
    };
    const renderJobs = (items) => {
        const body = document.getElementById('jobs-body');
        if (!body) return;
        const label = { success: '完成', failed: '失败', running: '运行中' };
        body.innerHTML = items.length ? items.map((job) => `<tr><td><span class="job-name">${escapeHTML(job.job_type)}</span></td><td><span class="job-status status-${escapeHTML(job.status)}">${label[job.status] || escapeHTML(job.status)}</span></td><td>${formatNumber(job.input_count)}</td><td>${formatNumber(job.success_count)}</td><td>${formatNumber(job.failed_count)}</td><td class="mono">${escapeHTML((job.started_at || '').slice(0, 16).replace('T', ' '))}</td><td>${escapeHTML(job.message)}</td><td><button class="table-action" type="button" data-job-detail="${Number(job.id)}">查看详情</button></td></tr>`).join('') : '<tr><td colspan="8" class="table-empty">暂无运行记录</td></tr>';
    };

    const adminState = { concertPage: 1, commentPage: 1 };

    const renderAdminStats = (payload) => {
        const totals = payload.totals || {};
        [['stat-concerts', totals.concerts], ['stat-comments', totals.comments], ['stat-artists', totals.artists], ['stat-cities', totals.cities]].forEach(([id, value]) => {
            const node = document.getElementById(id);
            if (node) node.textContent = formatNumber(value ?? 0);
        });
        const daysChart = getChart('admin-days-chart');
        const days = payload.recent_days || [];
        if (daysChart && days.length) {
            daysChart.setOption({ animationDuration: 500, grid: { left: 12, right: 16, top: 12, bottom: 12, containLabel: true }, tooltip: { ...chartTooltip, trigger: 'axis' }, xAxis: { type: 'category', data: days.map((item) => (item.date || '').slice(5)), axisLabel: chartText, axisLine: { lineStyle: { color: chartTheme.line } } }, yAxis: { type: 'value', splitLine: { lineStyle: { color: chartTheme.line } }, axisLabel: chartText }, series: [{ type: 'line', smooth: true, data: days.map((item) => item.count), symbolSize: 6, lineStyle: { color: chartTheme.lime, width: 2 }, itemStyle: { color: chartTheme.lime }, areaStyle: { color: 'rgba(220,255,88,.08)' } }] }, true);
        } else if (daysChart) {
            renderEmptyChart('admin-days-chart');
        }
        const sourcesChart = getChart('admin-sources-chart');
        const sources = payload.sources || [];
        if (sourcesChart && sources.length) {
            sourcesChart.setOption({ animationDuration: 500, color: ['#dcff58', '#5ed5c9', '#ff835c', '#8a98a3', '#b28dff'], tooltip: { ...chartTooltip, trigger: 'item', formatter: (params) => `${escapeHTML(params.name)}<br/>${formatNumber(params.value)} 场` }, legend: { bottom: 0, textStyle: { color: chartTheme.text, fontFamily: 'Fira Sans', fontSize: 10 }, itemWidth: 10, itemHeight: 10 }, series: [{ type: 'pie', radius: ['42%', '68%'], center: ['50%', '44%'], data: sources.map((item) => ({ name: item.source, value: item.count })), label: { color: chartTheme.text, fontFamily: 'Fira Sans', fontSize: 10 }, itemStyle: { borderColor: chartTheme.panel, borderWidth: 2 } }] }, true);
        } else if (sourcesChart) {
            renderEmptyChart('admin-sources-chart');
        }
    };

    const renderAdminConcerts = (payload) => {
        const body = document.getElementById('concert-admin-body');
        if (!body) return;
        const items = payload.items || [];
        const totalNode = document.getElementById('concert-total');
        if (totalNode) totalNode.textContent = `共 ${formatNumber(payload.total ?? 0)} 场 · 第 ${payload.page} / ${payload.pages} 页`;
        body.innerHTML = items.length ? items.map((concert) => `<tr>
            <td><input type="checkbox" class="concert-check" data-concert-id="${Number(concert.id)}" aria-label="选择场次 ${Number(concert.id)}"></td>
            <td class="mono">${Number(concert.id)}</td>
            <td>${escapeHTML(concert.artist_name)}</td>
            <td title="${escapeHTML(concert.concert_name)}">${escapeHTML((concert.concert_name || '').slice(0, 26))}${(concert.concert_name || '').length > 26 ? '…' : ''}</td>
            <td>${escapeHTML(concert.city)}</td>
            <td class="mono">${escapeHTML((concert.show_time || '').slice(0, 16).replace('T', ' '))}</td>
            <td class="mono">${escapeHTML(concert.price_text || '—')}</td>
            <td><span class="job-status status-${concert.sale_status === '售票中' ? 'success' : concert.sale_status === '已售罄' ? 'failed' : 'running'}">${escapeHTML(concert.sale_status)}</span></td>
            <td class="mono">${escapeHTML((concert.source_type || '').slice(0, 12))}</td>
            <td class="row-actions"><button class="table-action" type="button" data-edit-concert="${Number(concert.id)}">编辑</button><button class="table-action danger" type="button" data-delete-concert="${Number(concert.id)}">删除</button></td>
        </tr>`).join('') : '<tr><td colspan="10" class="table-empty">没有匹配的演唱会记录</td></tr>';
        const pager = document.getElementById('concert-pager');
        if (pager) pager.innerHTML = buildPager(payload.page, payload.pages, 'concert');
        updateBatchButton();
    };

    const renderAdminComments = (payload) => {
        const body = document.getElementById('comment-admin-body');
        if (!body) return;
        const items = payload.items || [];
        const totalNode = document.getElementById('comment-total');
        if (totalNode) totalNode.textContent = `共 ${formatNumber(payload.total ?? 0)} 条 · 第 ${payload.page} / ${payload.pages} 页`;
        body.innerHTML = items.length ? items.map((comment) => {
            const score = comment.sentiment_score;
            const sentimentLabel = score == null ? '未分析' : score >= 0.6 ? '正面' : score <= 0.4 ? '负面' : '中性';
            const sentimentClass = score == null ? 'running' : score >= 0.6 ? 'success' : score <= 0.4 ? 'failed' : 'running';
            return `<tr>
            <td class="mono">${Number(comment.id)}</td>
            <td class="mono">${comment.concert_id == null ? '—' : Number(comment.concert_id)}</td>
            <td title="${escapeHTML(comment.comment_text)}">${escapeHTML((comment.comment_text || '').slice(0, 48))}${(comment.comment_text || '').length > 48 ? '…' : ''}</td>
            <td class="mono">${escapeHTML((comment.comment_time || '').slice(0, 16).replace('T', ' '))}</td>
            <td class="mono">${formatNumber(comment.like_count ?? 0)}</td>
            <td>${escapeHTML(comment.user_region || '—')}</td>
            <td><span class="job-status status-${sentimentClass}">${sentimentLabel}</span></td>
            <td class="row-actions"><button class="table-action danger" type="button" data-delete-comment="${Number(comment.id)}">删除</button></td>
        </tr>`; }).join('') : '<tr><td colspan="8" class="table-empty">没有匹配的评论记录</td></tr>';
        const pager = document.getElementById('comment-pager');
        if (pager) pager.innerHTML = buildPager(payload.page, payload.pages, 'comment');
    };

    const buildPager = (page, pages, kind) => {
        const prev = `<button class="pager-btn" type="button" data-page-${kind}="${Math.max(1, page - 1)}" ${page <= 1 ? 'disabled' : ''}>上一页</button>`;
        const next = `<button class="pager-btn" type="button" data-page-${kind}="${Math.min(pages, page + 1)}" ${page >= pages ? 'disabled' : ''}>下一页</button>`;
        const dots = [];
        for (let i = 1; i <= pages && i <= 7; i += 1) {
            dots.push(`<button class="pager-btn ${i === page ? 'is-active' : ''}" type="button" data-page-${kind}="${i}">${i}</button>`);
        }
        return `${prev}${dots.join('')}${next}`;
    };

    const concertQuery = () => {
        const params = new URLSearchParams();
        const q = document.getElementById('concert-q')?.value?.trim();
        const artist = document.getElementById('concert-artist-filter')?.value;
        const city = document.getElementById('concert-city-filter')?.value;
        const status = document.getElementById('concert-status-filter')?.value;
        if (q) params.set('q', q);
        if (artist) params.set('artist', artist);
        if (city) params.set('city', city);
        if (status) params.set('status', status);
        params.set('page', adminState.concertPage);
        return params.toString();
    };
    const commentQuery = () => {
        const params = new URLSearchParams();
        const q = document.getElementById('comment-q')?.value?.trim();
        const artist = document.getElementById('comment-artist-filter')?.value;
        if (q) params.set('q', q);
        if (artist) params.set('artist', artist);
        params.set('page', adminState.commentPage);
        return params.toString();
    };

    const updateBatchButton = () => {
        const checked = document.querySelectorAll('.concert-check:checked').length;
        const button = document.querySelector('[data-concert-batch-delete]');
        if (button) button.disabled = checked === 0;
    };

    const initAdmin = () => {
        const refreshJobs = async () => {
            try { renderJobs((await fetchJSON('/admin/api/jobs')).items || []); } catch (error) { toast(error.message, 'error'); }
        };
        const previewImport = async () => {
            const form = document.getElementById('import-form');
            const file = form?.querySelector('input[type="file"]')?.files?.[0];
            if (!file) return toast('请先选择 CSV 文件', 'error');
            try { renderImportReport((await fetchJSON('/admin/api/import/preview', { method: 'POST', body: new FormData(form) })).report); } catch (error) { toast(error.message, 'error'); }
        };
        const loadConcerts = async (page = 1) => {
            adminState.concertPage = page;
            try {
                const payload = await fetchJSON(`/admin/api/concerts?${concertQuery()}`);
                renderAdminConcerts(payload);
            } catch (error) { toast(error.message, 'error'); }
        };
        const loadComments = async (page = 1) => {
            adminState.commentPage = page;
            try {
                const payload = await fetchJSON(`/admin/api/comments?${commentQuery()}`);
                renderAdminComments(payload);
            } catch (error) { toast(error.message, 'error'); }
        };
        const loadSummary = async () => {
            try {
                const summary = await fetchJSON('/admin/api/concerts/summary');
                [['concert-artist-filter', summary.artists], ['concert-city-filter', summary.cities], ['concert-status-filter', summary.statuses]].forEach(([id, values]) => {
                    const select = document.getElementById(id);
                    if (!select) return;
                    const current = select.value;
                    select.innerHTML = `<option value="">${id.includes('artist') ? '全部艺人' : id.includes('city') ? '全部城市' : '全部状态'}</option>` + (values || []).map((value) => `<option value="${escapeHTML(value)}">${escapeHTML(value)}</option>`).join('');
                    if (current) select.value = current;
                });
                const commentArtist = document.getElementById('comment-artist-filter');
                if (commentArtist) {
                    commentArtist.innerHTML = '<option value="">全部艺人</option>' + (summary.artists || []).map((value) => `<option value="${escapeHTML(value)}">${escapeHTML(value)}</option>`).join('');
                }
            } catch (error) { toast(error.message, 'error'); }
        };
        const loadStats = async () => {
            try { renderAdminStats(await fetchJSON('/admin/api/stats')); } catch (error) { toast(error.message, 'error'); }
        };

        document.querySelectorAll('[data-admin-tab]').forEach((tab) => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('[data-admin-tab]').forEach((node) => node.classList.remove('is-active'));
                document.querySelectorAll('[data-admin-pane]').forEach((node) => node.classList.remove('is-active'));
                tab.classList.add('is-active');
                const name = tab.dataset.adminTab;
                const pane = document.querySelector(`[data-admin-pane="${name}"]`);
                pane?.classList.add('is-active');
                if (name === 'dashboard') loadStats();
                if (name === 'concerts') { loadSummary(); loadConcerts(1); }
                if (name === 'comments') { loadSummary(); loadComments(1); }
                refreshIcons();
            });
        });

        document.querySelector('[data-refresh-jobs]')?.addEventListener('click', refreshJobs);
        document.querySelector('[data-preview-import]')?.addEventListener('click', previewImport);
        document.querySelector('#import-form input[type="file"]')?.addEventListener('change', (event) => {
            const label = document.querySelector('[data-file-name]');
            if (label) label.textContent = event.target.files?.[0]?.name || '选择 CSV 文件';
        });
        document.getElementById('jobs-body')?.addEventListener('click', async (event) => {
            const detailButton = event.target.closest('[data-job-detail]');
            if (detailButton) {
                try { renderJobDetail((await fetchJSON(`/admin/api/jobs/${Number(detailButton.dataset.jobDetail)}`)).job); } catch (error) { toast(error.message, 'error'); }
            }
            if (event.target.closest('[data-close-job-detail]')) {
                const detail = document.getElementById('job-detail');
                if (detail) detail.hidden = true;
            }
        });
        document.getElementById('job-detail')?.addEventListener('click', (event) => {
            if (event.target.closest('[data-close-job-detail]')) event.currentTarget.hidden = true;
        });

        document.querySelector('[data-concert-search]')?.addEventListener('click', () => loadConcerts(1));
        document.querySelector('[data-concert-reset]')?.addEventListener('click', () => {
            ['concert-q', 'concert-artist-filter', 'concert-city-filter', 'concert-status-filter'].forEach((id) => {
                const node = document.getElementById(id);
                if (node) node.value = '';
            });
            loadConcerts(1);
        });
        document.getElementById('concert-admin-body')?.addEventListener('click', async (event) => {
            if (event.target.closest('[data-delete-concert]')) {
                const id = Number(event.target.closest('[data-delete-concert]').dataset.deleteConcert);
                if (!confirm(`确认删除演唱会记录 #${id}？关联评论将一并删除。`)) return;
                try {
                    await fetchJSON(`/admin/api/concerts/${id}`, { method: 'DELETE' });
                    toast('场次已删除');
                    loadConcerts(adminState.concertPage);
                } catch (error) { toast(error.message, 'error'); }
            }
            if (event.target.closest('[data-edit-concert]')) {
                const id = Number(event.target.closest('[data-edit-concert]').dataset.editConcert);
                const newName = prompt('修改演唱会名称（留空取消）：');
                if (newName == null) return;
                const name = String(newName).trim();
                if (!name) return;
                try {
                    await fetchJSON(`/admin/api/concerts/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ concert_name: name }) });
                    toast('场次名称已更新');
                    loadConcerts(adminState.concertPage);
                } catch (error) { toast(error.message, 'error'); }
            }
            if (event.target.closest('.concert-check')) updateBatchButton();
        });
        document.querySelector('[data-check-all-concerts]')?.addEventListener('change', (event) => {
            document.querySelectorAll('.concert-check').forEach((node) => { node.checked = event.target.checked; });
            updateBatchButton();
        });
        document.querySelector('[data-concert-batch-delete]')?.addEventListener('click', async () => {
            const ids = [...document.querySelectorAll('.concert-check:checked')].map((node) => Number(node.dataset.concertId));
            if (!ids.length) return;
            if (!confirm(`确认批量删除 ${ids.length} 场演唱会？关联评论将一并删除。`)) return;
            try {
                const result = await fetchJSON('/admin/api/concerts/batch-delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) });
                toast(`已删除 ${result.deleted} 场`);
                loadConcerts(1);
            } catch (error) { toast(error.message, 'error'); }
        });
        document.getElementById('concert-pager')?.addEventListener('click', (event) => {
            const button = event.target.closest('[data-page-concert]');
            if (button) loadConcerts(Number(button.dataset.pageConcert));
        });

        document.querySelector('[data-comment-search]')?.addEventListener('click', () => loadComments(1));
        document.querySelector('[data-comment-reset]')?.addEventListener('click', () => {
            ['comment-q', 'comment-artist-filter'].forEach((id) => {
                const node = document.getElementById(id);
                if (node) node.value = '';
            });
            loadComments(1);
        });
        document.getElementById('comment-admin-body')?.addEventListener('click', async (event) => {
            if (event.target.closest('[data-delete-comment]')) {
                const id = Number(event.target.closest('[data-delete-comment]').dataset.deleteComment);
                if (!confirm(`确认删除评论 #${id}？`)) return;
                try {
                    await fetchJSON(`/admin/api/comments/${id}`, { method: 'DELETE' });
                    toast('评论已删除');
                    loadComments(adminState.commentPage);
                } catch (error) { toast(error.message, 'error'); }
            }
        });
        document.getElementById('comment-pager')?.addEventListener('click', (event) => {
            const button = event.target.closest('[data-page-comment]');
            if (button) loadComments(Number(button.dataset.pageComment));
        });

        document.querySelector('[data-run-analysis]')?.addEventListener('click', async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            try { await fetchJSON('/admin/api/analyze', { method: 'POST' }); toast('分析任务已完成'); await refreshJobs(); await loadStats(); } catch (error) { toast(error.message, 'error'); } finally { button.disabled = false; }
        });
        document.querySelector('[data-clear-cache]')?.addEventListener('click', async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            try { const result = await fetchJSON('/admin/api/cache/clear', { method: 'POST' }); toast(`已清空 ${result.cleared} 个缓存键`); } catch (error) { toast(error.message, 'error'); } finally { button.disabled = false; }
        });
        document.querySelector('[data-seed]')?.addEventListener('click', async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            try { const result = await fetchJSON('/admin/api/seed', { method: 'POST' }); toast(result.result.seeded ? '演示快照已写入' : '数据库已有演示数据'); await refreshJobs(); } catch (error) { toast(error.message, 'error'); } finally { button.disabled = false; }
        });
        document.getElementById('import-form')?.addEventListener('submit', async (event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const button = form.querySelector('button[type="submit"]');
            button.disabled = true;
            try {
                const result = await fetchJSON('/admin/api/import', { method: 'POST', body: new FormData(form) });
                renderImportReport(result.report || result.result);
                toast('CSV 导入已完成');
                await refreshJobs();
                form.reset();
                const label = document.querySelector('[data-file-name]');
                if (label) label.textContent = '选择 CSV 文件';
            } catch (error) { toast(error.message, 'error'); } finally { button.disabled = false; }
        });

        loadStats();
        refreshJobs();
    };

    refreshIcons();
    observeReveal();
    initTilt();
    if (page === 'dashboard') initDashboard();
    if (page === 'admin') initAdmin();
})();
